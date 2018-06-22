from flask import Flask, render_template, redirect, url_for, request, jsonify
from flask import flash, make_response
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Category, Item, User
from flask import session as login_session
import random
import string
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response

app = Flask(__name__)
engine = create_engine('sqlite:///catalog.db',
                       connect_args={'check_same_thread': False})
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)
session = DBSession()

CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Catalog Application"


# Create anti-forgery state token
@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    return render_template('login.html', STATE=state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps(
            'Current user is already connected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    # see if user exists, if not, add a new one
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += '" style = "width: 300px; height: 300px;border-radius: '
    output += '150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;">'
    print "done!"
    return output


# DISCONNECT - Revoke a current user's token and reset their login_session
@app.route('/gdisconnect')
def gdisconnect():
    access_token = login_session.get('access_token')
    if access_token is None:
        print 'Access Token is None'
        response = make_response(json.dumps(
            'Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    if result['status'] == '200':
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        return redirect(url_for('showCategories'))
    else:
        response = make_response(json.dumps(
            'Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response

# User Helper Functions


# Create a new user with data from login_session
def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


# Find user data with user_id
def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


# Find user id with user email
def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None

# Add routes


# JSON for all category data along with associated item data
@app.route('/catalog.json')
def CategoryItemJson():
    cats = session.query(Category).all()

    return jsonify(Categories=[
        (c.serialize, [i.serialize for i in session.query(Item).filter_by(
            category_id=c.id)]) for c in cats])


# JSON for all category names & IDs
@app.route('/categories.json')
def allCategoriesJson():
    categories = session.query(Category).all()
    return jsonify(Categories=[c.serialize for c in categories])


# JSON for all items data
@app.route('/items.json')
def allItemsJson():
    items = session.query(Item).all()
    return jsonify(Items=[i.serialize for i in items])


# JSON for all users data
@app.route('/users.json')
def allUsersJson():
    users = session.query(User).all()
    return jsonify(Users=[u.serialize for u in users])


# Home page
@app.route('/')
@app.route('/catalog/')
def showCategories():
    categories = session.query(Category).all()
    items = session.query(Item).all()

    # For latest items, show the last 10 items only if list size > 10
    if len(items) > 10:
        items = items[-10:]

    # Create a map with key=category.id, and value=category.name
    categoryMap = {}
    for category in categories:
        categoryMap[category.id] = category.name

    # Using categoryMap, create a list of tuples containing each item name
    # with its category name
    item_category_names = []
    for item in items:
        item_category_names.append((item.title, categoryMap[item.category_id]))

    if 'username' not in login_session:
        return render_template('index_public.html', categories=categories,
                               latest_items=item_category_names)
    else:
        return render_template('index.html', categories=categories,
                               latest_items=item_category_names)


# Show items of a specific category
@app.route('/catalog/<string:category_name>/items/')
def showItems(category_name):
    categories = session.query(Category).all()
    category = session.query(Category).filter_by(name=category_name).one()
    items = session.query(Item).filter_by(category_id=category.id).all()

    if 'username' not in login_session:
        return render_template('category_public.html', categories=categories,
                               items=items, category=category)
    else:
        return render_template('category.html', categories=categories,
                               items=items, category=category)


# Show details of a specific item
@app.route('/catalog/<string:category_name>/<string:item_title>/')
def itemDescription(category_name, item_title):
    item = session.query(Item).filter_by(title=item_title).one()

    if 'username' not in login_session:
        return render_template('item_public.html', item=item,
                               category_name=category_name)
    else:
        userID = getUserID(login_session['email'])
        if userID == item.user_id:
            return render_template('item.html', item=item,
                                   category_name=category_name)
        else:
            return render_template('item_public.html', item=item,
                                   category_name=category_name)


# Add a new item
@app.route('/catalog/additem/', methods=['GET', 'POST'])
def addItem():
    if 'username' not in login_session:
        return redirect('/login')
    # For post requests -> use the item details from the form data
    if request.method == 'POST':
        category = session.query(Category).filter_by(
            name=request.form['itemCategory']).one()
        newItem = Item(title=request.form['itemTitle'],
                       description=request.form['itemDescription'],
                       category_id=category.id,
                       user_id=login_session['user_id'])
        session.add(newItem)
        session.commit()
        return redirect(url_for('showCategories'))
    # For get requests -> render the form to collect item details
    else:
        categories = session.query(Category).all()
        return render_template('add_item.html', categories=categories)


# Add a new category
@app.route('/catalog/addcategory/', methods=['GET', 'POST'])
def addCategory():
    if 'username' not in login_session:
        return redirect('/login')
    # For post requests -> use the category name from the form data
    if request.method == 'POST':
        newCategory = Category(name=request.form['categoryName'])
        session.add(newCategory)
        session.commit()
        return redirect(url_for('showCategories'))
    # For get requests -> render the form to collect category name
    else:
        return render_template('add_category.html')


# Edit an existing item
@app.route('/catalog/<string:item_title>/edit/', methods=['GET', 'POST'])
def editItem(item_title):
    # User must be logged in to edit an item
    if 'username' not in login_session:
        return redirect('/login')
    # Check if the item belongs to the logged user
    userID = getUserID(login_session['email'])
    itemToEdit = session.query(Item).filter_by(title=item_title).one()
    # Item belongs to the user
    if userID == itemToEdit.user_id:
        # For post requests -> use the new item details from the form data
        if request.method == 'POST':
            if request.form['itemTitle']:
                itemToEdit.title = request.form['itemTitle']
            if request.form['itemDescription']:
                itemToEdit.description = request.form['itemDescription']
            if request.form['itemCategory']:
                category = session.query(Category).filter_by(
                    name=request.form['itemCategory']).one()
                itemToEdit.category_id = category.id
            session.add(itemToEdit)
            session.commit()
            return redirect(url_for('showCategories'))
        # For get requests -> render the form to collect item details
        else:
            categories = session.query(Category).all()
            return render_template('edit_item.html', item=itemToEdit,
                                   categories=categories)
    # Item doesn't belong to logged user, render an error message
    else:
        return render_template('permission_error.html',
                               message='edit %s' % item_title)


# Delete an existing item
@app.route('/catalog/<string:item_title>/delete/', methods=['GET', 'POST'])
def deleteItem(item_title):
    # User must be logged in to edit an item
    if 'username' not in login_session:
        return redirect('/login')
    userID = getUserID(login_session['email'])
    itemToDelete = session.query(Item).filter_by(title=item_title).one()
    # Check if the item belongs to the logged user
    if userID == itemToDelete.user_id:
        # For post requests -> delete the item
        if request.method == 'POST':
            session.delete(itemToDelete)
            session.commit()
            return redirect(url_for('showCategories'))
        # For get requests -> render the form to delete an item
        else:
            return render_template('delete_item.html', item_title=item_title)
    # Item doesn't belong to logged user, render an error message
    else:
        return render_template('permission_error.html',
                               message='delete %s' % item_title)

if __name__ == '__main__':
    app.secret_key = 'secret'
    app.debug = True
    app.run(host='0.0.0.0', port=8000)
