import Link from "next/link";

export default function Home() {
  return (
    <>
      <h1>LabGuard</h1>
      <p className="muted">
        College lab monitoring console — M1 project shell. No monitoring data is
        available yet; device telemetry arrives in a later milestone.
      </p>
      <div className="status-box">
        <p>
          API status: <Link href="/health">view live API health</Link>
        </p>
        <p className="muted">
          The health page reads from the API at runtime. If the API is not
          running, it reports that instead of showing data.
        </p>
      </div>
    </>
  );
}
