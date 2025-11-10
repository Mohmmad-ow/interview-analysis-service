import json
from typing import Dict, List, Optional
import asyncio
from loguru import logger
from app.config import settings
from google import genai

from app.models.analysis.response import QuestionAnalysis


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

    async def analyze_interview(
        self,
        transcript: str,
        job_description: str,
        questions: Optional[List[str]] = None,
    ) -> Dict:
        """
        Main analysis method that uses Gemini to evaluate the interview
        """
        try:
            prompt = self._build_analysis_prompt(transcript, job_description, questions)
            response = await self._call_gemini_api(prompt)
            return self._parse_analysis_response(response)

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            raise

    def _build_analysis_prompt(
        self,
        transcript: str,
        job_description: str,
        questions: Optional[List[str]] = None,
    ) -> str:
        """
        Build the prompt for Gemini analysis
        """
        # Could customize further based on job role, industry, etc.
        # {f"SPECIFIC QUESTIONS ASKED: {questions}" if questions else ""}
        base_prompt = f"""
        Analyze this job interview transcript and provide a comprehensive evaluation.

        JOB DESCRIPTION:
        {job_description}

        INTERVIEW TRANSCRIPT:
        {transcript}

        

        {f"POINTS OF INTEREST TO FOCUS ON: {', '.join(questions)}" if questions else ""}

        Please provide analysis in the following JSON format:
        {{
            "technical_score": 0.0-10.0,
            "communication_score": 0.0-10.0,
            "confidence_indicators": {{
                "clarity": 0.0-1.0,
                "articulation": 0.0-1.0,
                "engagement": 0.0-1.0
            }},
            "key_insights": [
                "list of key observations",
                "strengths and weaknesses",
                "specific recommendations",
                "add some predictions about candidate fit",
                "how the candidate compares to typical candidates for this role",
                "any potential red flags",
                "areas for improvements",
            ]
        }}

        Scoring Guidelines:
        - Technical Score: Relevance to job requirements, depth of knowledge, problem-solving ability
        - Communication Score: Clarity, structure, listening skills, articulation
        - Confidence Indicators: Based on language patterns, hesitation, assertiveness

        Be objective and provide constructive feedback.
        """

        return base_prompt

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

    def _parse_analysis_response(self, response_text: str) -> Dict:
        """
        Parse Gemini response into structured data
        """
        try:
            # Extract JSON from response (Gemini might wrap it in markdown)
            import re

            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)

            if json_match:
                analysis_data = json.loads(json_match.group())
            else:
                # Fallback: try to parse the entire response
                analysis_data = json.loads(response_text)

            # Validate required fields
            required_fields = [
                "technical_score",
                "communication_score",
                "confidence_indicators",
                "key_insights",
            ]
            for field in required_fields:
                if field not in analysis_data:
                    raise ValueError(f"Missing required field in analysis: {field}")

            return analysis_data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {response_text}")
            raise ValueError("Invalid response format from AI service")

    async def analyze_question(
        self, question: str, answer_transcript: str, job_context: str
    ) -> QuestionAnalysis:
        """
        Analyze individual question-answer pairs
        """
        prompt = f"""
        Analyze this specific interview question and answer:

        QUESTION: {question}
        ANSWER: {answer_transcript}
        JOB CONTEXT: {job_context}

        Provide scores and confidence level in JSON:
        {{
            "technical_score": 0-10,
            "communication_score": 0-10,
            "confidence_level": "high|medium|low"
        }}
        """

        try:
            response = await self._call_gemini_api(prompt)
            analysis_data = self._parse_analysis_response(response)

            return QuestionAnalysis(
                question_text=question,
                answer_transcript=answer_transcript,
                technical_score=analysis_data["technical_score"],
                communication_score=analysis_data["communication_score"],
                confidence_level=analysis_data["confidence_level"],
            )

        except Exception as e:
            logger.error(f"Question analysis failed: {e}")
            # Return default analysis on failure
            return QuestionAnalysis(
                question_text=question,
                answer_transcript=answer_transcript,
                technical_score=5.0,
                communication_score=5.0,
                confidence_level="medium",
            )


# Singleton instance
gemini_service = GeminiAnalysis()
