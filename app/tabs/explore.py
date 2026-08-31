"""Interactive related-keyword exploration for the current RAG response."""

import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


# Temporary search-result adapter. Replace this function with a Pinecone-backed
# endpoint when the RAG Chain exposes related-topic search.
MOCK_RELATED_SEARCH_RESULTS = {
    "민요": [
        ("아리랑", "대표적인 민요"),
        ("강강술래", "관련 민요"),
        ("정선아리랑", "지역 민요"),
    ],
    "노동요": [
        ("모내기노래", "농업 노동요"),
        ("방아타령", "생활 노동요"),
        ("베틀노래", "길쌈 관련 노동요"),
    ],
    "길쌈": [
        ("베틀", "전통 직조 도구"),
        ("베틀노래", "길쌈 관련 노래"),
        ("직조", "관련 전통 기술"),
    ],
    "조선": [
        ("태조", "관련 인물"),
        ("한양", "관련 공간"),
        ("조선 궁궐", "관련 문화유산"),
    ],
    "궁궐": [
        ("창덕궁", "관련 궁궐"),
        ("덕수궁", "관련 궁궐"),
        ("종묘", "관련 문화유산"),
    ],
    "창덕궁": [
        ("후원", "창덕궁의 공간"),
        ("인정전", "창덕궁의 전각"),
        ("경복궁", "관련 궁궐"),
    ],
}


# UI examples only; replace with source-grounded summaries from related search.
MOCK_TOPIC_SUMMARIES = {
    "아리랑": "‘아리랑’이라는 후렴을 중심으로 여러 지역에서 다양하게 전승되는 민요입니다.",
    "강강술래": "여럿이 손을 잡고 둥글게 돌며 노래하고 춤추는 전통 놀이입니다.",
    "정선아리랑": "강원도 정선 지역에서 전승되는 아리랑입니다.",
    "모내기노래": "논에 모를 심으면서 부르던 노동요입니다.",
    "방아타령": "방아를 찧는 일과 관련된 내용을 담은 민요입니다.",
    "베틀노래": "베틀로 옷감을 짜는 일을 소재로 부르는 민요입니다.",
    "베틀": "실을 엮어 옷감을 짜는 데 사용하는 전통 도구입니다.",
    "직조": "가로실과 세로실을 서로 엮어 옷감을 만드는 기술입니다.",
    "태조": "조선을 세운 첫 번째 왕 이성계입니다.",
    "한양": "조선의 수도로, 오늘날 서울의 옛 이름입니다.",
    "조선 궁궐": "조선 왕실이 생활하며 나랏일을 처리하던 궁궐들입니다.",
    "창덕궁": "조선 왕실의 궁궐로, 자연 지형과 어우러진 배치가 특징입니다.",
    "덕수궁": "서울에 있는 궁궐로, 대한제국의 역사와 관련이 깊은 곳입니다.",
    "종묘": "조선 왕과 왕비의 신주를 모시고 제사를 지내는 왕실 사당입니다.",
    "후원": "창덕궁 뒤편에 조성된 왕실 정원입니다.",
    "인정전": "창덕궁에서 중요한 국가 의식을 치르던 중심 전각입니다.",
    "경복궁": "조선의 중심 궁궐로, 서울에 세워진 왕실의 법궁입니다."
}


def render() -> None:
    st.subheader("문화유산 탐험 지도")
    st.caption("문화유산을 누르면 연관 키워드가 펼쳐집니다. 키워드를 다시 눌러 가지를 이어가 보세요.")
    result = st.session_state.get("last_result")
    if not result:
        st.info("질문하기 탭에서 답변을 받은 뒤 탐험 지도를 확인해 주세요.")
        return

    response = result.get("response", {})
    contexts = result.get("retrieved_contexts", [])
    title = next((item.get("title") for item in contexts if item.get("title")), None)
    if not title:
        st.info("이번 응답에는 탐험할 문화유산이 없습니다.")
        return

    keywords = result.get("related_keywords", response.get("related_keywords", []))
    payload = {
        "question": result.get("question", ""),
        "root": title,
        "keywords": keywords,
        "summaries": MOCK_TOPIC_SUMMARIES,
        "related": {
            key: [{"keyword": name, "relation": relation} for name, relation in values]
            for key, values in MOCK_RELATED_SEARCH_RESULTS.items()
        },
    }
    template = (Path(__file__).resolve().parents[1] / "components" / "exploration_map.html").read_text(encoding="utf-8")
    # Keep any response text inside JSON; never allow it to terminate the script.
    encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    components.html(template.replace("__EXPLORATION_DATA__", encoded), height=660, scrolling=False)
    st.caption("예시 데이터 · 현재 연관 키워드와 가지는 Mock입니다. 실제 Pinecone 검색은 아직 연결하지 않았습니다.")
