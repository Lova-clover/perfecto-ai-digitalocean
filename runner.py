#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import os, sys, time, argparse, json, yaml, re
from typing import List, Dict, Any, Optional

# ===== 1) 프로젝트 모듈 import =====
from langchain_core.documents import Document as LCDocument
from persona import generate_response_from_persona
from RAG.retriever_builder import build_retriever
from RAG.chain_builder import get_conversational_rag_chain, get_default_chain
from text_scraper import get_links, clean_html_parallel, filter_noise
from best_subtitle_extractor import load_best_subtitles_documents
from image_generator import generate_images_for_topic
from generate_timed_segments import generate_subtitle_from_script, generate_ass_subtitle
from video_maker import create_video_with_segments, add_subtitles_to_video, create_dark_text_video
from deep_translator import GoogleTranslator

# ===== 2) 유틸 =====
NOW = lambda: time.strftime('%Y-%m-%d %H:%M:%S')

def make_docs_from_web_query(query: str, n: int = 10) -> List[LCDocument]:
    urls = get_links(query, num=n)
    results = clean_html_parallel(urls)
    docs: List[LCDocument] = []
    for r in results:
        if r.get('success') and r.get('text'):
            txt = filter_noise(r['text'])
            if len(txt) >= 200:
                docs.append(LCDocument(page_content=txt, metadata={"source": r['url']}))
    return docs

# ===== 3) 페르소나 로딩 =====
def load_personas(personas_file: str, group: Optional[str] = None) -> List[Dict[str, Any]]:
    with open(personas_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    if isinstance(data, dict) and 'groups' in data:
        grp = group or data.get('default_group') or next(iter(data['groups'].keys()))
        personas = data['groups'].get(grp)
        if not personas:
            raise SystemExit(f"No personas under group '{grp}' in {personas_file}")
        return personas
    elif isinstance(data, list):
        return data
    else:
        raise SystemExit(f"Unsupported personas.yaml schema: {type(data)}")

# ===== 4) RAG/NoRAG 단일 페르소나 실행 =====
def run_persona_step(pcfg: Dict[str, Any], prev: List[str], system_prompt: str) -> Dict[str, Any]:
    name = pcfg.get('name', 'Persona')
    text = pcfg.get('text', '')
    rag_mode = pcfg.get('rag', 'none')  # none|web|youtube
    yt_channel = pcfg.get('youtube_channel')

    joined_prev = "\n\n".join(f"[이전] {o}" for o in prev if o)
    prompt = f"{joined_prev}\n\n지시:\n{text}" if joined_prev else text

    retriever = None
    sources = []
    if rag_mode == 'web':
        docs = make_docs_from_web_query(text)
        if docs:
            retriever = build_retriever(docs)
    elif rag_mode == 'youtube' and yt_channel:
        subtitle_docs = load_best_subtitles_documents(yt_channel)
        if subtitle_docs:
            retriever = build_retriever(subtitle_docs)

    if retriever:
        chain = get_conversational_rag_chain(retriever, system_prompt)
        res = chain.invoke({"input": prompt})
        out_text = res.get("answer") or res.get("result") or res.get("content") or ""
        for d in res.get("source_documents", []) or []:
            snippet = (d.page_content or "").strip()
            if len(snippet) > 300:
                snippet = snippet[:300] + "..."
            sources.append({"content": snippet, "source": d.metadata.get("source", "N/A")})
    else:
        out_text = generate_response_from_persona(prompt, system_prompt)

    return {"name": name, "output": out_text.strip(), "sources": sources}

# ===== 5) 제목/키워드 추출 =====
TITLE_SYS = """
당신은 유튜브 숏폼 제목 생성기다.
규칙:
1) 반드시 한국어만.
2) 한 줄만. 리스트/번호/불릿/설명 금지.
3) 이모지/영문/해시태그/특수기호 남발 금지.
4) 10자 이내.
정답(제목)만 출력하라.
""".strip()
TOPIC_SYS = "당신은 텍스트에서 핵심 키워드만 간결히 추출합니다."

def extract_title_and_topic(script_text: str) -> tuple[str, str]:
    tchain = get_default_chain(TITLE_SYS)
    title = (tchain.invoke({"question": f"다음 스크립트에서 8단어 이내 제목만: \n\n{script_text}\n\n제목:"}) or "").strip()
    kchain = get_default_chain(TOPIC_SYS)
    topic = (kchain.invoke({"question": f"이미지 생성을 위한 2~3 키워드 또는 10단어 이하 구문: \n\n{script_text}\n\n키워드:"}) or "").strip()
    return title, topic

# ===== 6) 잡 실행 =====
def run_job(job: Dict[str, Any], personas: List[Dict[str, Any]]) -> Dict[str, Any]:
    print(f"[{NOW()}] ▶️ Start job: {job.get('name','(noname)')}")
    system_prompt = job.get('system_prompt', '당신은 유능한 AI입니다.')

    style = job.get('style', 'basic')  # basic|emotional
    include_voice = job.get('include_voice', style != 'emotional')
    tts_provider = job.get('tts_provider', 'elevenlabs')  # elevenlabs|polly
    tts_template = job.get('tts_template', 'korean_female')
    polly_voice_key = job.get('polly_voice_key', 'Seoyeon')
    subtitle_lang = job.get('subtitle_lang', 'ko')
    bgm_path = job.get('bgm_path') or ''
    out_dir = job.get('out_dir', 'assets/auto')
    os.makedirs(out_dir, exist_ok=True)

    # 6.1 페르소나 체인
    outputs: List[str] = []
    logs: List[Dict[str, Any]] = []
    for p in personas:
        res = run_persona_step(p, outputs, system_prompt)
        outputs.append(res['output'])
        logs.append(res)
    if not outputs:
        raise RuntimeError('No persona produced output')
    script_text = outputs[-1]

    # 6.2 제목/키워드
    title, topic = extract_title_and_topic(script_text)
    if not title:
        title = job.get('fallback_title', '제목 없음')
    image_query = topic or title

    # 6.3 오디오/세그먼트/자막
    segments = []
    full_audio_path = os.path.join(out_dir, 'audio.mp3')
    ass_path = os.path.join(out_dir, 'subtitle.ass')

    if style != 'emotional' and include_voice:
        prov = 'elevenlabs' if tts_provider.lower().startswith('eleven') else 'polly'
        template = tts_template if prov == 'elevenlabs' else polly_voice_key
        segments, _, _ = generate_subtitle_from_script(
            script_text=script_text,
            ass_path=ass_path,
            full_audio_file_path=full_audio_path,
            provider=prov,
            template=template,
            subtitle_lang=subtitle_lang,
            translate_only_if_english=False,
        )
    else:
        # 무성/감성 텍스트: 길이 기반 더미 세그먼트, 자막(선택)
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s*', script_text) if s.strip()]
        if not sents:
            sents = [script_text.strip()]
        wpm = 150
        total_words = len(script_text.split())
        total_dur = max(5.0, (total_words / wpm) * 60.0)
        total_chars = sum(len(s) for s in sents) or 1
        cur = 0.0
        for s in sents:
            seg_dur = max(1.5, total_dur * (len(s) / total_chars))
            segments.append({"start": cur, "end": cur + seg_dur, "text": s})
            cur += seg_dur
        # 필요 시 스타일 템플릿 이름 바꾸세요
        generate_ass_subtitle(segments, ass_path, template_name='default')

    # 6.4 이미지
    image_paths: List[str] = []
    if style != 'emotional':
        try:
            try:
                q_en = GoogleTranslator(source='ko', target='en').translate(image_query)
            except Exception:
                q_en = image_query
            image_paths = generate_images_for_topic(q_en, max(3, len(segments) or 3))
        except Exception as e:
            print('[WARN] image generation failed, use placeholder:', e)
            os.makedirs('assets', exist_ok=True)
            ph = os.path.join('assets', 'default.jpg')
            if not os.path.exists(ph):
                import requests
                url = 'https://images.pexels.com/photos/936043/pexels-photo-936043.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2'
                with open(ph, 'wb') as f:
                    f.write(requests.get(url, timeout=20).content)
            image_paths = [ph] * max(3, len(segments) or 3)

    # 6.5 비디오
    temp_video = os.path.join(out_dir, 'temp.mp4')
    final_video = os.path.join(out_dir, 'final.mp4')

    if style == 'emotional':
        created = create_dark_text_video(
            script_text=script_text,
            title_text=title,
            audio_path=None,
            bgm_path=bgm_path,
            save_path=temp_video,
        )
        final_path = created
    else:
        created = create_video_with_segments(
            image_paths=image_paths,
            segments=segments,
            audio_path=full_audio_path if include_voice and os.path.exists(full_audio_path) else None,
            topic_title=title,
            include_topic_title=True,
            bgm_path=bgm_path,
            save_path=temp_video,
        )
        final_path = add_subtitles_to_video(created, ass_path, output_path=final_video)

    # 6.6 업로드(옵션)
    youtube_url = None
    if job.get('upload', False):
        try:
            from upload import upload_to_youtube
            youtube_url = upload_to_youtube(final_path, title=title)
            print(f"[{NOW()}] 📤 uploaded: {youtube_url}")
        except Exception as e:
            print(f"[{NOW()}] [WARN] upload failed: {e}")

    print(f"[{NOW()}] ✅ done: {final_path}")
    return {
        "title": title,
        "topic": image_query,
        "video_path": final_path,
        "youtube_url": youtube_url,
        "personas": logs,
    }

# ===== 7) 엔트리포인트 =====
def main():
    ap = argparse.ArgumentParser(description='DigitalOcean Ubuntu Runner')
    ap.add_argument('-c','--config', default='job_config.yaml')
    ap.add_argument('--personas-file', default=None, help='override personas.yaml path')
    ap.add_argument('--personas-group', default=None, help='group name inside personas.yaml')
    args = ap.parse_args()

    with open(args.config, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f) or {}

    jobs = cfg.get('jobs', [])
    if not jobs:
        raise SystemExit('No jobs in config')

    # personas 파일 경로 결정
    personas_file = args.personas_file or cfg.get('personas_file', 'personas.yaml')
    personas_group = args.personas_group or cfg.get('personas_group')

    all_results = []
    for job in jobs:
        # job 레벨에서 다른 그룹을 지정할 수도 있음
        group = job.get('personas_group', personas_group)
        pfile = job.get('personas_file', personas_file)
        personas = load_personas(pfile, group=group)
        try:
            res = run_job(job, personas)
            all_results.append(res)
        except Exception as e:
            print(f"[{NOW()}] ❌ job failed: {e}")

    print("\n=== SUMMARY ===")
    for i, r in enumerate(all_results, 1):
        print(f"[{i}] {r['title']} -> {r['video_path']}" + (f" | {r['youtube_url']}" if r.get('youtube_url') else ''))

if __name__ == '__main__':
    main()