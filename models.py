from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from datetime import datetime, timedelta

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(unique=True)
    username: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    profile: Mapped['Profile'] = relationship(back_populates='user', uselist=False)
    given_ratings: Mapped['Rating'] = relationship(back_populates='rater')
    profile_views: Mapped['ProfileView'] = relationship(back_populates='viewer')

class Profile(Base):
    __tablename__ = 'profiles'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    description: Mapped[str]
    category: Mapped[str]
    photo_id: Mapped[str] = mapped_column(nullable=True)
    video_id: Mapped[str] = mapped_column(nullable=True)
    is_verified: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    delete_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now()+timedelta(days=30))
    user: Mapped['User'] = relationship(back_populates='profile')
    received_ratings: Mapped['Rating'] = relationship(back_populates='profile')
    viewed_by: Mapped['ProfileView'] = relationship(back_populates='profile')

class Rating(Base):
    __tablename__ = 'ratings'
    id: Mapped[int] = mapped_column(primary_key=True)
    rater_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    profile_id: Mapped[int] = mapped_column(ForeignKey('profiles.id'))
    score: Mapped[float]
    comment: Mapped[str] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    rater: Mapped['User'] = relationship(back_populates='given_ratings')
    profile: Mapped['Profile'] = relationship(back_populates='received_ratings')

class ProfileView(Base):
    __tablename__ = 'profile_views'
    id: Mapped[int] = mapped_column(primary_key=True)
    viewer_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    profile_id: Mapped[int] = mapped_column(ForeignKey('profiles.id'))
    viewed_at: Mapped[datetime] = mapped_column(default=datetime.now)
    viewer: Mapped['User'] = relationship(back_populates='profile_views')
    profile: Mapped['Profile'] = relationship(back_populates='viewed_by')
