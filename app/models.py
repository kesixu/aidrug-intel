"""AI for Science 大陆情报系统 — 数据模型"""
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Float, Text, DateTime, Boolean, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "aidrug.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class IntelEntry(Base):
    __tablename__ = "intel_entries"

    id = Column(String, primary_key=True)  # intel_YYYYMMDD_NNN
    date_published = Column(String, nullable=False)
    date_captured = Column(String, nullable=False)
    source_department = Column(String, nullable=False)
    source_url = Column(Text, nullable=False)
    title = Column(String, nullable=False)
    category = Column(String, nullable=False)  # 政策发布|实施细则|资金申报|人才政策|监管动态|企业动态|学术会议|产业数据
    region_tier = Column(String, nullable=False)  # 亦庄BDA|市级|京津冀|全国
    original_excerpt = Column(Text, default="")
    ai_interpretation = Column(Text, default="")
    relevance_score_overall = Column(Integer, default=0)
    relevance_score_az = Column(Integer, default=0)
    relevance_score_trustpathbot = Column(Integer, default=0)
    relevance_score_talent = Column(Integer, default=0)
    relevance_score_funding = Column(Integer, default=0)
    relevance_reasoning = Column(Text, default="")
    forecast = Column(Text, default="")
    recommended_action = Column(Text, default="")
    follow_up_flag = Column(Boolean, default=False)
    related_entry_ids = Column(JSON, default=list)
    user_note = Column(Text, default="")
    user_status = Column(String, default="")  # 已读|需跟进|已过时
    policy_family = Column(String, default="")  # 政策家族标识
    policy_stage = Column(String, default="")  # 发布|解读|配套细则|资金申报|结果产出
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "date_published": self.date_published,
            "date_captured": self.date_captured,
            "source_department": self.source_department,
            "source_url": self.source_url,
            "title": self.title,
            "category": self.category,
            "region_tier": self.region_tier,
            "original_excerpt": self.original_excerpt,
            "ai_interpretation": self.ai_interpretation,
            "relevance_score": {
                "overall": self.relevance_score_overall,
                "az_beijing": self.relevance_score_az,
                "trustpathbot": self.relevance_score_trustpathbot,
                "talent_program": self.relevance_score_talent,
                "funding_opportunity": self.relevance_score_funding,
            },
            "relevance_reasoning": self.relevance_reasoning,
            "forecast": self.forecast,
            "recommended_action": self.recommended_action,
            "follow_up_flag": self.follow_up_flag,
            "related_entry_ids": self.related_entry_ids or [],
            "user_note": self.user_note,
            "user_status": self.user_status,
            "policy_family": self.policy_family,
            "policy_stage": self.policy_stage,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


Base.metadata.create_all(bind=engine)
