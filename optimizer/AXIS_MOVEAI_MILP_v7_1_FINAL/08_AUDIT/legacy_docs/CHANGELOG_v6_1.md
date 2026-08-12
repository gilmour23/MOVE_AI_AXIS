# v6 → v6.1 변경사항

1. `CHANGE_LATEST_ARRIVAL` 완화 시 Candidate Train을 다시 생성하도록 수정.
2. `MODIFY_SERVICE`로 수량·latest/earliest arrival·max earliness·blocked origins 복수조건 동시 처리.
3. Proposal UUID / negotiation round / version / parent proposal 추가.
4. stale proposal UUID/version 검증 추가.
5. optional `Path Slot Capacity` 제약 추가.
6. optional `Wagon / Locomotive Availability` 제약 추가.
7. FINAL `RAIL_UNSERVED` 의미 수정:
   - 수락했지만 KORAIL 미확정 물량만 포함.
   - 미응답/거절 예상수요는 `NONCOMMITTED_FORECAST_NEED.csv`로 분리.
8. Effective due / earliest arrival을 Proposal Detail에 명시.
9. 자동검증 102/102 PASS.
