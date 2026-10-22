## Current Step in Spec-Driven Development

**Now: 4. Review (Human)** — C0~C7 Data Fabric 구현·검증 보고 완료 (2026-10-22). 일반 회귀 119개, Neo4j 전체 13개, 후속 provenance/통합 8개와 v3 비교 browser 검증을 기록했다. 실제 GPT 14회+F7 추가 2회 및 근거 coverage 한계를 보고서에 남겼다. 사용자 검토 대기이며 Review/Reflect를 대신 수행하지 않는다.

### SDD Step

1. Design (Human+AI)
2. Plan (AI+Human)
3. Implement (AI)
4. Review (Human)
5. Reflect (AI, into plan)

Design은 초기 Human과 AI가 함께 Docs의 Spec들을 설계하는 단계이다.  
Plan에서는 Implement를 위해 Plan을 계획하여 IMPLEMENTATION_PLAN.md에 반영한다.
이후에는 Plan - Implement - Review - Reflect 루프를 돈다.  
Implement에서는 AI가 IMPLEMENTATION_PLAN.md를 기반으로 구현하고 IMPLEMENTATION_REPORT와 그 외 관련 문서(PRD 등)들에 기록한다. 
Review에서는 Human이 Review하여 REVIEW.md에 반영한다.  
Reflect에서는 AI가 Human Review를 docs/IMPLEMENTATION_PLAN.md에 반영한다. 이 문서가 프로젝트의 PLAN 문서다.
