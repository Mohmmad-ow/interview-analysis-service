# from sqlalchemy.orm import Session
# from fastapi import Depends
# from app.api.dependencies import get_db_session
# from app.database.repository import AnalysisRepository, AuditRepository


# class CombinedRepository:
#     def __init__(self, session: Session):
#         self.analysis = AnalysisRepository(session)
#         self.audit = AuditRepository(session)


# def get_combined_repository(
#     db: Session = Depends(get_db_session),
# ) -> CombinedRepository:
#     return CombinedRepository(db)
