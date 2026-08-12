# KORAIL Optional Operations Constraints v6.1

실제 KORAIL 운영 데이터가 확보될 경우에만 활성화한다. 실제 값이 없으면 빈 배열로 둔다.

## JSON

```json
{
  "path_slot_capacity": [
    {
      "service_family": "GYEONGBU",
      "start_time": "2026-08-11 00:00",
      "end_time": "2026-08-11 23:00",
      "max_trains": 2
    }
  ],
  "resource_capacity": [
    {
      "start_time": "2026-08-11 00:00",
      "end_time": "2026-08-11 23:00",
      "available_wagons": 100,
      "available_locomotives": 3
    }
  ]
}
```

`service_family`, `origin_terminal`, `destination_terminal`은 Path Slot rule에서 선택 필터다.

## 주의

위 숫자는 예시 형식일 뿐이며 프로젝트 실제 입력값으로 사용하지 않는다.
