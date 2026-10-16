# REVIEW

### 역할 

사용자의 Review를 관리하고, 
이를 기반으로 문서에 다음 구현 plan을 IMPLEMENTATION.PLAN.md에 기록한다.

### 2026/10/16 10:03
- 다음과 같이 semantic layer를 구분하도록 전반을 수정한다.
- OFF: 원천 C4I 도구와 일반 계산만 사용. Semantic 해석·관계 해소·동일성 판정 코드를 호출하지 않음.
- ON: Semantic Layer가 제공하는 개념·관계·동일성 해석을 추가로 사용.
- 각 체계간 상충하는 정보는 없도록 수정한다. 