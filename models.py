from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timedelta
Base = declarative_base()
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    profile = relationship('Profile', back_populates='user', uselist=False)
    given_ratings = relationship('Rating', back_populates='rater')

class Profile(Base):
    __tablename__ = 'profiles'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    description = Column(String)
    photo_id = Column(String)
    video_id = Column(String)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    delete_at = Column(DateTime, default=datetime.utcnow()+timedelta(days=30))
    user = relationship('User', back_populates='profile')
    received_ratings = relationship('Rating', back_populates='profile')

class Rating(Base):
    __tablename__ = 'ratings'
    id = Column(Integer, primary_key=True)
    rater_id = Column(Integer, ForeignKey('users.id'))
    profile_id = Column(Integer, ForeignKey('profiles.id'))
    score = Column(Float)
    comment = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    rater = relationship('User', back_populates='given_ratings')
    profile = relationship('Profile', back_populates='received_ratings')




