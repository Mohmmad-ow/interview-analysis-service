from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings
from app.core.logging import logger
from typing import Generator


class DatabaseManager:
    def __init__(self):
        # Don't make __init__ async - use a sync constructor
        self.engine: Engine = self._setup_engine()
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )
        self.create_tables()
        logger.info("DatabaseManager initialized successfully")

    def _setup_engine(self) -> Engine:
        """Initialize database connection - SYNC method"""
        try:
            database_url = (
                f"mysql+mysqlconnector://"
                f"{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}"
                f"@{settings.MYSQL_HOST}/{settings.MYSQL_DATABASE}"
            )

            engine = create_engine(
                database_url,
                pool_pre_ping=True,
                pool_recycle=300,
                echo=settings.DEBUG,
            )
            logger.info("Database engine created successfully")
            return engine
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def get_session(self) -> Generator[Session, None, None]:
        """Generator that yields a session per request"""
        session = self.SessionLocal()
        try:
            yield session
            logger.debug("Database session yielded successfully")
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
            logger.debug("Database session closed")

    def create_tables(self):
        """Create all tables (for development)"""
        try:
            from app.database.models import Base

            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise


# Global database instance - this is fine
db_manager = DatabaseManager()
