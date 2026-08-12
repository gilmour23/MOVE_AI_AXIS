# AXIS Chatbot Negotiation Schema v6.1

## 원칙

챗봇은 **운송 의사결정을 하지 않는다.**

```text
선사 자연어
→ Intent / 서비스조건 구조화
→ stale proposal 검증
→ 전체 선사 Candidate 재생성
→ 공동 MILP 재최적화
→ 새로운 Carrier Proposal
```

## 권장 Action

### 1. 서비스 수락

```json
{
  "proposal_id": "PROP0003",
  "proposal_uuid": "...",
  "proposal_version": 1,
  "action": "ACCEPT_SERVICE"
}
```

열차 자체는 KORAIL이 Final에서 다시 바꿀 수 있다.

### 2. Exact Plan 수락

```json
{
  "proposal_id": "PROP0003",
  "proposal_uuid": "...",
  "proposal_version": 1,
  "action": "ACCEPT_EXACT_PLAN"
}
```

현재 source/train까지 고정한다.

### 3. 다른 옵션 요청

```json
{
  "proposal_id": "PROP0003",
  "action": "REJECT_OPTION"
}
```

이번 옵션만 차단하고 대안을 탐색한다.

### 4. 철도서비스 자체 거절

```json
{
  "proposal_id": "PROP0003",
  "action": "DECLINE_RAIL_SERVICE"
}
```

### 5. 복수 조건 수정

```json
{
  "proposal_id": "PROP0010",
  "proposal_uuid": "...",
  "proposal_version": 1,
  "action": "MODIFY_SERVICE",
  "constraints": {
    "quantity": 12,
    "latest_arrival": "2026-08-14 18:00",
    "earliest_arrival": "2026-08-13 00:00",
    "max_earliness_hours": 48,
    "blocked_origins": ["BUSAN"]
  },
  "commit": false
}
```

`commit=false`: 수정된 Counterproposal 요청.

`commit=true`: 수정조건 자체를 Carrier Commitment로 확정.

---

# Negotiation round

최상위 JSON:

```json
{
  "negotiation_round": 2,
  "proposal_actions": []
}
```

새 Proposal 출력에는:

- `proposal_uuid`
- `negotiation_round`
- `proposal_version`
- `parent_proposal_id`

가 포함된다.

챗봇이 오래된 UUID/version을 보내면 optimizer가 stale request를 거부한다.

---

# 자연어 예시

> “8개 말고 12개로 하고 14일 전에는 도착시키지 마.”

→ `MODIFY_SERVICE(quantity=12, earliest_arrival=...)`

> “이 열차는 싫은데 다른 안 있어?”

→ `REJECT_OPTION`

> “이번 주는 철도 안 쓸게.”

→ `DECLINE_RAIL_SERVICE`

> “하루 더 늦어도 괜찮아.”

→ `MODIFY_SERVICE(latest_arrival=+24h)`

v6.1에서는 이 완화된 latest-arrival을 **Candidate Train 생성 전** 반영하므로 실제 늦은 열차가 새 탐색후보로 추가된다.
