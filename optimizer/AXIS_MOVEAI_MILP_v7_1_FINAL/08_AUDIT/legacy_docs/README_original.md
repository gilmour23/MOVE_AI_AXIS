# AXIS MILP v6.1 FINAL

## 목적

**KORAIL AXIS가 복수 선사의 공컨 데이터를 공동 분석하여 각 선사에게 철도운송안을 먼저 제안하고, 선사가 챗봇으로 수락·수정한 Carrier Commitment를 다시 공동최적화하여 KORAIL 최종 공컨 열차 운영계획으로 전환하는 시스템.**

## 실행모드

1. `PROPOSAL` — 모든 선사 데이터로 잠정 운송안 생성
2. `NEGOTIATION` — 챗봇 조건을 반영해 전체 재최적화
3. `FINAL` — 확정 Commitment만으로 KORAIL 최종 운행계획 생성

## 주요 파일

- `MILP_FORMULATION_v6_1.md`
- `CHATBOT_NEGOTIATION_SCHEMA_v6_1.md`
- `OPERATIONS_SCHEMA_v6_1.md`
- `IMPLEMENTATION_AUDIT_v6_1.md`
- `code/axis_milp_v6_1.py`
- `code/verify_v6_1.py`
- `input_data/`
- `results/`

## 핵심 출력

- Carrier Proposal
- KORAIL Train Plan
- Station Stop Work Plan
- Segment Load
- Rail Unserved
- Carrier Commitment Status
- Operational Constraint Audit

## 검증

`118 / 118 PASS`

## 중요 가정

- Candidate timetable: prototype 6-hour scenario
- Minimum consolidation level 50%: 연구/해커톤 scenario, KORAIL 공식 손익기준 아님
- 실제 path capacity, wagon, locomotive availability는 데이터 확보 시 optional constraint로 활성화
