"""UI 개발용 ServiceResponse 예시.

실제 RAG Chain이 준비되면 이 파일 대신 API 응답을 사용한다.
"""

SOURCE_NAME = "한국민족문화대백과사전"
SOURCE_URL = "https://encykorea.aks.ac.kr/Article/E0008547"


def citation(
    *,
    content: str,
    title: str = "길쌈노래",
    section: str = "definition",
    chunk_id: str = "aks:E0008547:e8fa3ea6d4b9:definition:0001",
    retrieval_rank: int = 1,
    retrieval_score: float = 0.92,
) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": "aks:E0008547",
        "title": title,
        "source_url": SOURCE_URL,
        "section": section,
        "retrieval_rank": retrieval_rank,
        "retrieval_score": retrieval_score,
        "content": content,
    }


RESPONSES = {
    "answered": {
        "response_type": "answered",
        "message": "길쌈노래는 여성들이 길쌈을 하면서 부르던 민요입니다. 일을 함께하며 박자를 맞추고 힘든 작업을 덜어 내는 역할을 했습니다.",
        "retrieved_contexts": [
            citation(content="여성들이 길쌈을 하면서 부르는 민요."),
            citation(
                content="길쌈은 실을 내어 옷감을 짜는 일을 말한다.",
                section="related_term",
                chunk_id="aks:E0008547:e8fa3ea6d4b9:related_term:0002",
                retrieval_rank=2,
                retrieval_score=0.86,
            ),
            citation(
                content="길쌈노래는 노동요의 한 갈래로 분류된다.",
                section="classification",
                chunk_id="aks:E0008547:e8fa3ea6d4b9:classification:0003",
                retrieval_rank=3,
                retrieval_score=0.79,
            ),
        ],
        "used_chunk_ids": ["aks:E0008547:e8fa3ea6d4b9:definition:0001"],
        "related_keywords": [
            {"keyword": "민요", "relation": "유형"},
            {"keyword": "노동요", "relation": "분류"},
            {"keyword": "길쌈", "relation": "관련 작업"},
        ],
        "citations": [citation(content="여성들이 길쌈을 하면서 부르는 민요.")],
        "clarification": None,
        "premise_correction": None,
    },
    "insufficient_evidence": {
        "response_type": "insufficient_evidence",
        "message": "현재 검색된 공식 자료만으로는 이 질문을 확인하기 어렵습니다. 확인 가능한 다른 문화유산 관련 질문을 해 주세요.",
        "retrieved_contexts": [],
        "used_chunk_ids": [],
        "related_keywords": [],
        "citations": [],
        "clarification": None,
        "premise_correction": None,
    },
    "needs_clarification": {
        "response_type": "needs_clarification",
        "message": "어떤 대상을 말씀하시는지 확인이 필요합니다.",
        "retrieved_contexts": [],
        "used_chunk_ids": [],
        "related_keywords": [],
        "citations": [],
        "clarification": {
            "reason_code": "ambiguous_entity",
            "question": "어떤 궁궐을 말씀하시는지 알려주시겠어요?",
            "options": [
                {"id": "option-1", "label": "경복궁", "source_chunk_ids": []},
                {"id": "option-2", "label": "창덕궁", "source_chunk_ids": []},
                {"id": "option-3", "label": "덕수궁", "source_chunk_ids": []},
            ],
        },
        "premise_correction": None,
    },
    "corrected_premise": {
        "response_type": "corrected_premise",
        "message": "확인된 내용을 바탕으로 바로잡아 설명해 드릴게요.",
        "retrieved_contexts": [
            citation(
                content="경복궁은 조선 초기의 법궁으로 1395년에 창건되었다.",
                title="경복궁",
                chunk_id="aks:E0008547:gyeongbokgung:definition:0001",
            )
        ],
        "used_chunk_ids": ["aks:E0008547:gyeongbokgung:definition:0001"],
        "related_keywords": [
            {"keyword": "조선", "relation": "시대"},
            {"keyword": "궁궐", "relation": "유형"},
            {"keyword": "창덕궁", "relation": "관련 궁궐"},
        ],
        "citations": [
            citation(
                content="경복궁은 조선 초기의 법궁으로 1395년에 창건되었다.",
                title="경복궁",
                chunk_id="aks:E0008547:gyeongbokgung:definition:0001",
            )
        ],
        "clarification": None,
        "premise_correction": {
            "original_premise": "경복궁은 조선 후기 궁궐이다.",
            "corrected_premise": "경복궁은 1395년에 창건된 조선 초기의 법궁입니다.",
        },
    },
    "safety_refusal": {
        "response_type": "safety_refusal",
        "message": "서비스의 설정이나 비밀 정보는 안내할 수 없습니다. 문화유산 자료에 관한 질문을 해 주세요.",
        "retrieved_contexts": [],
        "used_chunk_ids": [],
        "related_keywords": [],
        "citations": [],
        "clarification": None,
        "premise_correction": None,
    },
    "out_of_scope": {
        "response_type": "out_of_scope",
        "message": "현재 서비스는 한국민족문화대백과사전의 문화유산 자료를 안내하는 범위에서 답변합니다.",
        "retrieved_contexts": [],
        "used_chunk_ids": [],
        "related_keywords": [],
        "citations": [],
        "clarification": None,
        "premise_correction": None,
    },
}
