# AXIS MILP v6.1 구현 최종 감사

## 판정

**현재 서비스 목적에 맞게 v6.1 Freeze 가능.**

### PASS

- 전체 선사 공동 최적화
- 선사별 ownership 유지
- KORAIL이 선사별 Proposal 생성
- 챗봇 조건 → 전체 공동 재최적화
- ACCEPT / MODIFY / REJECT OPTION / DECLINE 구분
- FINAL에서는 확정 Carrier Commitment만 사용
- 기한 완화 시 Candidate Train 탐색공간 실제 확장
- 복수조건 `MODIFY_SERVICE`
- Proposal UUID/round/version
- optional Path Slot
- optional Wagon/Locomotive Capacity
- 22개 directed service path
- intermediate pickup/drop-off
- integer container assignment
- physical segment capacity

## 회귀결과

기본 Proposal 시나리오는 v6와 동일하게 유지됨.

- Forecast Need: 118 TEU
- Rail Proposal: 109 TEU
- Provisional Train: 2

Mixed Final:

- Carrier Commitment: 37 TEU
- KORAIL Confirmed: 37 TEU
- Final Train: 1

Single 5 TEU Accept:

- Commitment: 5 TEU
- KORAIL Confirmed: 0 TEU
- Final Train: 0

즉 소규모 수락만으로 최소 consolidation 조건을 만족하지 못하면 KORAIL이 전용열차를 강제 운행하지 않는다.

## v6 Critical Bug 수정 확인

`PROP0010`의 기존 latest due `2026-08-11 10:00`을 `2026-08-12 10:00`으로 완화하고 earliest arrival을 `2026-08-11 12:00`으로 지정했다.

v6.1 Candidate set에는 새로:

- 8/11 14:00
- 8/11 20:00
- 8/12 02:00
- 8/12 08:00

도착 후보가 생성되었다.

즉 협의조건 완화가 실제 탐색공간을 넓힌다.

## Operational Constraint 기능 검증

### Path Slot = 0

- Rail served: 0
- Train: 0

### Available Locomotive/Wagon = 0

- Rail served: 0
- Train: 0

따라서 실제 KORAIL 자원 데이터가 제공되면 동일 구조에 바로 연결 가능하다.

## 자동검증

**102 / 102 PASS**

검증파일: `results/VERIFICATION_CHECKS_v6_1.csv`

## 발표 시 주의

현재 숫자는 synthetic timetable 및 50% Minimum Consolidation Level을 적용한 시나리오 결과다. 실제 KORAIL 운행가능 train path, 선로용량, 화차·기관차 가용량이 확보되면 입력만 교체/활성화하여 재계산한다.
