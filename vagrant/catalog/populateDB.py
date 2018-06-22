from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
 
from database_setup import Category, Base, Item, User
 
engine = create_engine('sqlite:///catalog.db')
# Bind the engine to the metadata of the Base class so that the
# declaratives can be accessed through a DBSession instance
Base.metadata.bind = engine
 
DBSession = sessionmaker(bind=engine)
# A DBSession() instance establishes all conversations with the database
# and represents a "staging zone" for all the objects loaded into the
# database session object. Any change made against the objects in the
# session won't be persisted into the database until you call
# session.commit(). If you're not happy about the changes, you can
# revert all of them back to the last commit by calling
# session.rollback()
session = DBSession()

categories = ['Soccer', 'Basketball', 'Baseball', 'Hockey', 'Tennis', 'Skating']

user = User(name='Amr', email='dummymail@udacity.com',
            picture='https://goo.gl/bvh1jr')
session.add(user)
session.commit()

# Add categories
for cat_name in categories:
    category = Category(name=cat_name)
    session.add(category)
    session.commit()

# Add items

item1 = Item(title='Ball', description='The ball', user_id=1,  category_id=1)
session.add(item1)
session.commit()

item2= Item(title='Dribbling Goggles',
             description='Help prevent the player from looking down',
             category_id=2, user_id=1)
session.add(item2)
session.commit()

item3= Item(title='Launch Angle Tee',
             description='Teaches players the proper swing approach angles',
             category_id=3, user_id=1)
session.add(item3)
session.commit()

print item1.serialize
print item2.serialize
print item3.serialize
print "finished"
