# 압구정 실거래 전광판

## 세팅 순서
1. **API 키 받기**: data.go.kr 가입 → "국토교통부_아파트 매매 실거래가 상세 자료" 활용신청 → 일반 인증키 복사
2. **저장소 만들기**: GitHub에서 Public 저장소 생성 후 이 폴더의 파일 전체를 업로드 (`.github` 폴더 포함)
3. **키 등록**: 저장소 Settings → Secrets and variables → Actions → New repository secret
   이름 `MOLIT_KEY`, 값에 인증키
4. **Pages 켜기**: Settings → Pages → Branch `main` / `(root)` 저장
5. **최초 전체 수집**: Actions 탭 → "실거래 자동 갱신" → Run workflow → backfill 체크 후 실행
6. 로그 끝에 나오는 **구역 미지정 단지**를 `zones.json`의 overrides에 추가
7. 이후 평일 낮에 매시간 자동 갱신 (Actions 탭에서 수동 실행도 가능)

## 주의
- 저장소는 Public이므로 고객 정보·매물 DB는 절대 올리지 마세요.
- 인증키는 코드에 직접 쓰지 말고 반드시 Secrets에만 넣으세요.
- 지금 들어 있는 data.json은 화면 확인용 샘플이며, 첫 실행 때 실제 데이터로 교체됩니다.
