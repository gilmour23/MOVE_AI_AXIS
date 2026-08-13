/**
 * 배포 헬스체크 (Vercel Serverless Function).
 *
 * 이 함수가 응답하면 api/ 디렉터리가 함수로 인식됐다는 뜻이다.
 * 실제 키 값은 절대 반환하지 않고 설정 여부(boolean)만 노출한다.
 */

export default function handler(_request, response) {
  response.status(200).json({
    ok: true,
    service: "moveai-axis",
    runtime: `node ${process.versions.node}`,
    gemini: Boolean(process.env.GEMINI_API_KEY),
  });
}
