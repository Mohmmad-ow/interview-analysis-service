import json
from typing import Dict, List, Optional
import asyncio
from loguru import logger
from app.config import settings
from google import genai

from app.models.analysis.response import (
    StructuredResumeData,
    ScoreBreakdown,
    SkillsMatch,
)


class GeminiAnalysis:
    def __init__(self):
        self.client = None
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL
        self._initialize_client()

    def _initialize_client(self):
        """Initialize Gemini client with API key"""
        try:
            self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
            logger.info("Gemini client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            raise

    # ==================== DOCUMENT ANALYSIS METHODS ====================

    async def analyze_document(
        self,
        extracted_text: str,
        job_description: str,
        required_skills: List[str],
        preferred_skills: Optional[List[str]] = None,
    ) -> Dict:
        """
        Analyze resume/document text and extract structured information with scoring
        """
        try:
            prompt = self._build_document_analysis_prompt(
                extracted_text, job_description, required_skills, preferred_skills or []
            )
            response = await self._call_gemini_api(prompt)
            return self._parse_document_analysis_response(
                response, required_skills, preferred_skills or []
            )

        except Exception as e:
            logger.error(f"Document analysis failed: {e}")
            raise

    def _build_document_analysis_prompt(
        self,
        extracted_text: str,
        job_description: str,
        required_skills: List[str],
        preferred_skills: List[str],
    ) -> str:
        """
        Build the prompt for document/resume analysis
        """
        prompt = f"""
        Analyze this resume document and extract structured information. Then score the candidate against the job requirements.

        JOB DESCRIPTION:
        {job_description}

        REQUIRED SKILLS: {', '.join(required_skills)}
        PREFERRED SKILLS: {', '.join(preferred_skills)}

        RESUME TEXT:
        {extracted_text}

        Please provide analysis in the following EXACT JSON format:
        {{
            "structured_data": {{
                "name": "full name or null",
                "email": "email or null", 
                "phone": "phone number or null",
                "education": [
                    {{
                        "institution": "institution name",
                        "degree": "degree obtained", 
                        "field_of_study": "field of study or null",
                        "start_year": 2018,
                        "end_year": 2022,
                        "gpa": 3.8
                    }}
                ],
                "work_experience": [
                    {{
                        "company": "company name",
                        "title": "job title",
                        "start_date": "start date",
                        "end_date": "end date or null",
                        "description": "role description",
                        "duration_months": 24
                    }}
                ],
                "skills": ["skill1", "skill2", "skill3"],
                "certifications": ["cert1", "cert2"],
                "languages": ["language1", "language2"],
                "summary": "professional summary or null"
            }},
            "question_for_interview": ["question1", "question2", ...] or null,
            "overall_score": 0-100,
            "score_breakdown": {{
                "skills_score": 0-100,
                "experience_score": 0-100, 
                "education_score": 0-100,
                "overall_fit": 0-100
            }},
            "skills_match": {{
                "required_skills_matched": ["skill1", "skill2"],
                "preferred_skills_matched": ["skill3"],
                "missing_required_skills": ["skill4"],
                "missing_preferred_skills": ["skill5"],
                "skill_match_percentage": 75.5
            }},
            "key_insights": [
                "Key strength 1",
                "Key strength 2", 
                "Area for improvement 1",
                "Recommendation 1"
            ]
        }}

        Scoring Guidelines:
        - Overall Score: Overall suitability for the role (0-100)
        - Skills Score: Match between candidate skills and required skills (0-100)
        - Experience Score: Relevance and depth of work experience (0-100) 
        - Education Score: Relevance of education background (0-100)
        - Overall Fit: Cultural and role fit based on entire profile (0-100)
        - Questions for Interview: Generate relevant questions to ask the candidate in an interview based on their resume and job description.

        Be objective and focus on factual information from the resume.
        """

        return prompt

    def _parse_document_analysis_response(
        self,
        response_text: str,
        required_skills: List[str],
        preferred_skills: List[str],
    ) -> Dict:
        """
        Parse Gemini response for document analysis
        """
        try:
            import re

            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)

            if json_match:
                analysis_data = json.loads(json_match.group())
            else:
                analysis_data = json.loads(response_text)

            # Validate required structure
            required_structure = [
                "structured_data",
                "overall_score",
                "score_breakdown",
                "skills_match",
                "key_insights",
            ]
            for field in required_structure:
                if field not in analysis_data:
                    raise ValueError(
                        f"Missing required field in document analysis: {field}"
                    )

            # Validate scores are within range
            if not (0 <= analysis_data["overall_score"] <= 100):
                raise ValueError("Overall score must be between 0 and 100")

            # Ensure skills_match has all required fields
            skills_match = analysis_data["skills_match"]
            required_skills_fields = [
                "required_skills_matched",
                "preferred_skills_matched",
                "missing_required_skills",
                "missing_preferred_skills",
                "skill_match_percentage",
            ]
            for field in required_skills_fields:
                if field not in skills_match:
                    raise ValueError(f"Missing skills_match field: {field}")

            # Calculate actual skill match percentage for validation
            actual_percentage = (
                len(skills_match["required_skills_matched"]) / len(required_skills)
            ) * 100
            if abs(actual_percentage - skills_match["skill_match_percentage"]) > 20:
                logger.warning(
                    f"Skill match percentage seems off. Calculated: {actual_percentage}, Reported: {skills_match['skill_match_percentage']}"
                )

            return analysis_data

        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to parse Gemini document response as JSON: {response_text}"
            )
            raise ValueError(
                "Invalid response format from AI service for document analysis"
            )

    async def analyze_document_batch(
        self, documents: List[Dict], job_description: str, required_skills: List[str]
    ) -> List[Dict]:
        """
        Analyze multiple documents in batch (for efficiency)
        """
        try:
            # Process documents sequentially for now
            # You could optimize this with concurrent processing later
            results = []
            for doc in documents:
                result = await self.analyze_document(
                    doc["text"], job_description, required_skills
                )
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Batch document analysis failed: {e}")
            raise

    async def _call_gemini_api(self, prompt: str) -> str:
        """
        Make actual API call to Gemini
        """
        if not self.client:
            raise ValueError("Gemini client not initialized")
        try:
            # Note: Gemini API is synchronous, so we'll use asyncio.to_thread

            response = await asyncio.to_thread(
                self.client.models.generate_content, model=self.model, contents=[prompt]
            )
            # Some SDK versions return `.text`, others return nested objects; normalize to string
            return getattr(response, "text", str(response))

        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise


# Singleton instance
gemini_service = GeminiAnalysis()
