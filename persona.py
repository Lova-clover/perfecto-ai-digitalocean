from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq  # Groq LLM 사용 시
import os

def generate_response_from_persona(prompt_text: str) -> str:
    llm = ChatGroq(api_key=os.getenv("GROQ_API_KEY", ""), model_name="llama3-8b-8192")
    output_parser = StrOutputParser()

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """너는 콘텐츠 제작 전문가 그룹의 일원으로, 특정 역할을 수행한다.

- 사용자 입력은 너의 역할에 대한 지시이며, 필요한 경우 이전 페르소나의 응답이 함께 제공된다.
- 역할에 맞는 관점과 방식으로 응답하여라.
- 반드시 한국어로 응답하고, 핵심적인 인사이트 중심으로 요약하라.
- 불필요한 설명이나 영어, 장황한 말투는 피하라.

너는 감독, 트렌드 분석가, 시나리오 작가, 마케터, 심리학자 등 다양한 역할로 활동할 수 있다.
"""
        ),
        ("human", "{question}")
    ])

    chain = prompt | llm | output_parser

    try:
        return chain.invoke({"question": prompt_text}).strip()
    except Exception as e:
        return f"⚠️ 응답 생성 실패: {e}"
