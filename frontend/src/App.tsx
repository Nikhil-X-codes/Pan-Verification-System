import { FormEvent, useEffect, useRef, useState } from "react";

type ApiResult = {
  status: "success" | "error";
  error_code: string | null;
  data?: { pan: string; name: string } | null;
  billed: boolean;
  message?: string;
};
type Entry = { pan: string; outcome: string; time: string };
type View =
  | { kind: "idle" }
  | { kind: "loading"; slow: boolean }
  | { kind: "result"; result: ApiResult }
  | { kind: "error"; message: string; billed: boolean | null };
type Attempt = { pan: string; key: string };
const STORAGE_KEY = "idto.history";
const masked = (pan: string) => `${pan.slice(0, 5)}****${pan.slice(-1)}`;

export function validation(pan: string): string {
  if (!pan) return "Enter a PAN to begin.";
  if (!/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(pan))
    return "Use five letters, four digits, then one letter.";
  if (!"PCHFATBLJG".includes(pan[3]))
    return "The fourth letter must be P, C, H, F, A, T, B, L, J or G.";
  return "";
}

function readHistory(): Entry[] {
  try {
    const value: unknown = JSON.parse(
      localStorage.getItem(STORAGE_KEY) ?? "[]",
    );
    if (!Array.isArray(value)) return [];
    return value
      .filter((item: unknown): item is Entry => {
        if (typeof item !== "object" || item === null) return false;
        const entry = item as Partial<Entry>;
        return (
          typeof entry.pan === "string" &&
          /^[A-Z]{5}\*{4}[A-Z]$/.test(entry.pan) &&
          (entry.outcome === "Found" || entry.outcome === "Not found") &&
          typeof entry.time === "string" &&
          Number.isFinite(Date.parse(entry.time))
        );
      })
      .slice(0, 20);
  } catch {
    return [];
  }
}

function isResult(value: unknown): value is ApiResult {
  if (typeof value !== "object" || value === null) return false;
  const result = value as Partial<ApiResult>;
  if (
    typeof result.billed !== "boolean" ||
    (result.error_code !== null && typeof result.error_code !== "string")
  )
    return false;
  if (result.status === "error") return typeof result.message === "string";
  if (result.status !== "success") return false;
  if (result.error_code === "IDTO_202") return result.data === null;
  return (
    result.error_code === null &&
    typeof result.data?.name === "string" &&
    typeof result.data.pan === "string" &&
    /^[A-Z]{5}\*{4}[A-Z]$/.test(result.data.pan)
  );
}

export default function App() {
  const [pan, setPan] = useState("");
  const [view, setView] = useState<View>({ kind: "idle" });
  const [history, setHistory] = useState<Entry[]>(readHistory);
  const attempt = useRef<Attempt | null>(null);
  const busy = useRef(false);
  const error = validation(pan);

  useEffect(() => {
    if (view.kind !== "loading") return;
    const timer = window.setTimeout(
      () =>
        setView((current) =>
          current.kind === "loading"
            ? { kind: "loading", slow: true }
            : current,
        ),
      1500,
    );
    return () => window.clearTimeout(timer);
  }, [view.kind]);

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (busy.current || validation(pan)) return;
    busy.current = true;
    if (!attempt.current || attempt.current.pan !== pan)
      attempt.current = { pan, key: crypto.randomUUID() };
    const current = attempt.current;
    setView({ kind: "loading", slow: false });
    try {
      for (let retry = 0; retry <= 3; retry++) {
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 6000);
        let result: Response;
        try {
          result = await fetch("/api/verify/pan", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Idempotency-Key": current.key,
            },
            body: JSON.stringify({ pan: current.pan }),
            signal: controller.signal,
          });
        } finally {
          window.clearTimeout(timeout);
        }
        const data: unknown = await result.json();
        if (!isResult(data)) {
          setView({
            kind: "error",
            message:
              "The server returned an unexpected response. Retry this attempt.",
            billed: null,
          });
          return;
        }
        if (
          result.status === 409 &&
          data.error_code === "IDTO_010" &&
          retry < 3
        ) {
          await new Promise((resolve) => window.setTimeout(resolve, 1000));
          continue;
        }
        if (!result.ok || data.status === "error") {
          setView({
            kind: "error",
            message:
              data.message ??
              "Verification could not finish. Retry this attempt.",
            billed: data.billed,
          });
          return;
        }
        setView({ kind: "result", result: data });
        const entry = {
          pan: masked(current.pan),
          outcome: data.error_code === "IDTO_202" ? "Not found" : "Found",
          time: new Date().toISOString(),
        };
        const entries = [entry, ...history].slice(0, 20);
        setHistory(entries);
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
        } catch {
          setHistory(entries);
        }
        attempt.current = null;
        return;
      }
    } catch {
      setView({
        kind: "error",
        message:
          "Connection interrupted. The result is unknown. Retry to safely check this attempt.",
        billed: null,
      });
    } finally {
      busy.current = false;
    }
  }

  return (
    <div className="shell">
      <header className="header">
        <a href="/" className="brand" aria-label="IDTO home">
          <span className="brand-mark" aria-hidden="true">
            i
          </span>
          IDTO
          <span className="brand-divider" />
          <span>Identity tools</span>
        </a>
        <span className="demo-badge">DEMO ENVIRONMENT</span>
      </header>
      <main>
        <section className="intro">
          <p className="eyebrow">IDENTITY, WITH CLARITY</p>
          <h1>
            One PAN.
            <br />
            <span>A clear answer.</span>
          </h1>
          <p className="lede">
            Verify a Permanent Account Number and get a clear result. Safe
            retries keep every attempt consistent.
          </p>
          <div className="trust">
            <span aria-hidden="true">✓</span> Masked results{" "}
            <span aria-hidden="true">·</span> Safe to retry
          </div>
        </section>
        <section className="verify-card" aria-labelledby="verify-title">
          <div className="card-heading">
            <span className="step">01</span>
            <div>
              <p className="eyebrow">QUICK CHECK</p>
              <h2 id="verify-title">Verify a PAN</h2>
            </div>
          </div>
          <p className="card-description">
            Enter a PAN to check its verification status.
          </p>
          <form onSubmit={(event) => void submit(event)}>
            <label htmlFor="pan">Permanent Account Number</label>
            <input
              id="pan"
              name="pan"
              value={pan}
              maxLength={10}
              placeholder="ABCPE1234F"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              aria-describedby="pan-help"
              aria-invalid={pan.length > 0 && Boolean(error)}
              disabled={view.kind === "loading"}
              onChange={(event) => {
                setPan(event.target.value.toUpperCase());
                attempt.current = null;
                setView({ kind: "idle" });
              }}
            />
            <p
              id="pan-help"
              className={pan && error ? "field-help invalid" : "field-help"}
            >
              {error || "PAN format looks good."}
            </p>
            <button
              className="primary"
              type="submit"
              disabled={Boolean(error) || view.kind === "loading"}
              onClick={(event) => {
                if (event.detail > 1) event.preventDefault();
              }}
            >
              {view.kind === "loading" ? (
                <>
                  <span className="spinner" aria-hidden="true" />
                  Verifying...
                </>
              ) : (
                <>
                  Verify PAN <span aria-hidden="true">↗</span>
                </>
              )}
            </button>
          </form>
          <div aria-live="polite" aria-atomic="true" className="result-area">
            {view.kind === "loading" && (
              <p className="pending">
                {view.slow
                  ? "Still checking, this can take a few seconds"
                  : "Checking your PAN..."}
              </p>
            )}
            {view.kind === "result" && (
              <div className="result success">
                <span className="eyebrow">
                  {view.result.error_code === "IDTO_202"
                    ? "NO MATCH"
                    : "VERIFIED"}
                </span>
                <h3>
                  {view.result.data ? view.result.data.name : "PAN not found"}
                </h3>
                {view.result.data ? (
                  <p className="masked-pan">{view.result.data.pan}</p>
                ) : (
                  <p>No matching PAN was found in this demo.</p>
                )}
                <span className="charge-label">
                  {view.result.billed ? "Charged" : "Not charged"}
                </span>
              </div>
            )}
            {view.kind === "error" && (
              <div className="result failure">
                <h3>Unable to complete verification</h3>
                <p>{view.message}</p>
                {view.billed !== null && (
                  <span className="charge-label">
                    {view.billed ? "Charged" : "Not charged"}
                  </span>
                )}
                <button
                  type="button"
                  className="retry"
                  onClick={(event) => {
                    if (event.detail <= 1) void submit();
                  }}
                >
                  Retry
                </button>
              </div>
            )}
          </div>
          <p className="privacy-note">
            Only masked PANs are saved in your browser history.
          </p>
        </section>
        <section className="history" aria-labelledby="history-title">
          <div className="history-heading">
            <h2 id="history-title">Recent verifications</h2>
            <span>THIS BROWSER · LAST 20</span>
          </div>
          {history.length ? (
            <ol>
              {history.map((entry, index) => (
                <li key={`${entry.time}-${index}`}>
                  <span className="history-icon" aria-hidden="true">
                    ✓
                  </span>
                  <div>
                    <strong>{entry.pan}</strong>
                    <time dateTime={entry.time}>
                      {new Date(entry.time).toLocaleString()}
                    </time>
                  </div>
                  <span className="history-outcome">{entry.outcome}</span>
                </li>
              ))}
            </ol>
          ) : (
            <div className="empty-history">
              <span aria-hidden="true">◎</span>
              <p>
                Your checks will appear here.
                <small>Masked PAN, result and time. Nothing more.</small>
              </p>
            </div>
          )}
        </section>
      </main>
      <footer>
        <span>IDTO / PAN Verification</span>
        <span>Assignment demo · Sample data only</span>
      </footer>
    </div>
  );
}
