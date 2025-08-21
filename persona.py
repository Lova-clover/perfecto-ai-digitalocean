# /srv/app/persona.py
import os
import re
import unicodedata
from typing import Optional

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 기본 시스템 프롬프트(잡에서 따로 주지 않으면 이걸 사용)
DEFAULT_SYS_PROMPT = """너는 콘텐츠 제작 전문가 그룹의 일원이다.

- 사용자 입력은 너의 역할에 대한 지시이며, 필요한 경우 이전 페르소나의 응답이 함께 제공된다.
- 역할에 맞는 관점과 방식으로 응답하여라.
- 반드시 한국어로 응답하고, 핵심 인사이트 중심으로 짧고 간결하게 요약하라.
- 불필요한 설명이나 영어, 장황한 말투는 피하라.

규칙:
1) 반드시 **한국어만** 사용한다.
2) 영어 알파벳, 이모지, 의미 없는 특수문자는 사용하지 않는다.
3) 2~4문장 이내로 간결하게 작성한다.
"""

# 간단한 한국어 정리(영문/제어문자/이상 특수문자 제거)
_ALLOW = r"[^0-9\u3131-\u318E\uAC00-\uD7A3\u1100-\u11FF\s\.,!?\"'()\-\:\;…~%]"
def _sanitize_korean(text: str, ko_only: bool = True) -> str:
    t = unicodedata.normalize("NFC", text)
    t = "".join(ch for ch in t if ch == "\n" or unicodedata.category(ch)[0] != "C")
    t = t.replace("\u00A0", " ").replace("\u200b", "").replace("\u3000", " ")
    t = t.replace("“", "\"").replace("”", "\"").replace("’", "'")
    if ko_only:
        t = re.sub(r"[A-Za-z]+", "", t)  # 영문 제거
    t = re.sub(_ALLOW, " ", t)          # 허용 외 특수문자 제거
    t = re.sub(r"[ \t]+", " ", t).strip()
    return t

def generate_response_from_persona(
    prompt_text: str,
    system_text: Optional[str] = None,    # runner에서 잡의 system_prompt를 넘길 수 있게
) -> str:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not set. Put it in /srv/secure/perfecto-ai.env and source it.")

    # ✅ 올바른 키워드: groq_api_key
    llm = ChatGroq(model_name="llama3-8b-8192", groq_api_key=key, temperature=0.3)

    sys_prompt = (system_text or os.getenv("PERSONA_SYS_PROMPT") or DEFAULT_SYS_PROMPT).strip()

    prompt = ChatPromptTemplate.from_messages([
        ("system", sys_prompt),
        ("human", "{question}")
    ])

    chain = prompt | llm | StrOutputParser()
    raw = chain.invoke({"question": prompt_text}).strip()
    return _sanitize_korean(raw, ko_only=True)
