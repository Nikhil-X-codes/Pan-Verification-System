import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const found = {
  status: "success",
  error_code: null,
  data: { pan: "ABCPE****F", name: "RAHUL SHARMA" },
  billed: true,
};
const missing = {
  status: "success",
  error_code: "IDTO_202",
  data: null,
  billed: true,
};
const unavailable = {
  status: "error",
  error_code: "IDTO_008",
  data: null,
  message: "Retry this request with the same idempotency key.",
  billed: false,
};
const pending = {
  ...unavailable,
  error_code: "IDTO_010",
  message: "Still processing. Retry with the same key.",
};
const fetchMock = vi.fn<typeof fetch>();
const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

function keyAt(index: number): string {
  return (
    new Headers(fetchMock.mock.calls[index][1]?.headers).get(
      "Idempotency-Key",
    ) ?? ""
  );
}

async function fill(pan = "ABCPE1234F") {
  await userEvent.type(screen.getByLabelText("Permanent Account Number"), pan);
}

beforeEach(() => {
  localStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("PAN verification", () => {
  it("validates format and holder type with an accessible reason", async () => {
    render(<App />);
    expect(screen.getByRole("button", { name: "Verify PAN" })).toBeDisabled();
    await fill("ABC");
    expect(
      screen.getByText("Use five letters, four digits, then one letter."),
    ).toBeVisible();
    await userEvent.clear(screen.getByLabelText("Permanent Account Number"));
    await fill("ABCXE1234F");
    expect(screen.getByText(/The fourth letter must/)).toBeVisible();
    expect(screen.getByLabelText("Permanent Account Number")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("normalizes input, renders found and stores masked history", async () => {
    fetchMock.mockResolvedValue(reply(found));
    render(<App />);
    await fill("abcpe1234f");
    await userEvent.click(screen.getByRole("button", { name: "Verify PAN" }));
    expect(await screen.findByText("RAHUL SHARMA")).toBeVisible();
    expect(screen.getByText("Charged")).toBeVisible();
    expect(keyAt(0)).toMatch(/^[a-f0-9-]{36}$/);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/verify/pan");
    const stored = localStorage.getItem("idto.history") ?? "";
    expect(stored).toContain("ABCPE****F");
    expect(stored).not.toContain("ABCPE1234F");
  });

  it("renders a billable not found response", async () => {
    fetchMock.mockResolvedValue(reply(missing));
    render(<App />);
    await fill("ABCPE0000F");
    await userEvent.click(screen.getByRole("button", { name: "Verify PAN" }));
    expect(await screen.findByText("PAN not found")).toBeVisible();
    expect(screen.getByText("Charged")).toBeVisible();
  });

  it("takes the billing label directly from the API", async () => {
    fetchMock.mockResolvedValue(reply({ ...found, billed: false }));
    render(<App />);
    await fill();
    await userEvent.click(screen.getByRole("button", { name: "Verify PAN" }));
    expect(await screen.findByText("Not charged")).toBeVisible();
  });

  it("reuses the same UUID after a server failure", async () => {
    fetchMock
      .mockResolvedValueOnce(reply(unavailable, 503))
      .mockResolvedValueOnce(reply(found));
    render(<App />);
    await fill();
    await userEvent.click(screen.getByRole("button", { name: "Verify PAN" }));
    expect(await screen.findByText(unavailable.message)).toBeVisible();
    expect(screen.getByText("Not charged")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("RAHUL SHARMA")).toBeVisible();
    expect(keyAt(1)).toBe(keyAt(0));
  });

  it("starts a new attempt after the PAN changes", async () => {
    fetchMock
      .mockResolvedValueOnce(reply(unavailable, 503))
      .mockResolvedValueOnce(reply(missing));
    render(<App />);
    await fill();
    await userEvent.click(screen.getByRole("button", { name: "Verify PAN" }));
    await screen.findByRole("button", { name: "Retry" });
    await userEvent.clear(screen.getByLabelText("Permanent Account Number"));
    await fill("ABCPE0000F");
    await userEvent.click(screen.getByRole("button", { name: "Verify PAN" }));
    await screen.findByText("PAN not found");
    expect(keyAt(1)).not.toBe(keyAt(0));
  });

  it("gives a new key to a new verification after success", async () => {
    fetchMock.mockImplementation(async () => reply(found));
    render(<App />);
    await fill();
    await userEvent.click(screen.getByRole("button", { name: "Verify PAN" }));
    await screen.findByText("RAHUL SHARMA");
    await userEvent.click(screen.getByRole("button", { name: "Verify PAN" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(keyAt(1)).not.toBe(keyAt(0));
  });

  it("prevents double click requests", async () => {
    let finish: ((response: Response) => void) | undefined;
    fetchMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    render(<App />);
    await fill();
    await userEvent.dblClick(
      screen.getByRole("button", { name: "Verify PAN" }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Verifying..." })).toBeDisabled();
    await act(async () => finish?.(reply(found)));
  });

  it("prevents a second click after a fast response", async () => {
    fetchMock.mockImplementation(async () => reply(found));
    render(<App />);
    await fill();
    await userEvent.click(screen.getByRole("button", { name: "Verify PAN" }));
    await screen.findByText("RAHUL SHARMA");
    fireEvent.click(screen.getByRole("button", { name: "Verify PAN" }), {
      detail: 2,
    });
    await act(async () => {});
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows delayed loading copy after 1.5 seconds", async () => {
    vi.useFakeTimers();
    let finish: ((response: Response) => void) | undefined;
    fetchMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    render(<App />);
    fireEvent.change(screen.getByLabelText("Permanent Account Number"), {
      target: { value: "ABCPE1234F" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify PAN" }));
    expect(screen.getByText("Checking your PAN...")).toBeVisible();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(
      screen.getByText("Still checking, this can take a few seconds"),
    ).toBeVisible();
    await act(async () => finish?.(reply(found)));
  });

  it("stops after three automatic retries and retains the key for manual retry", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(async () => reply(pending, 409));
    render(<App />);
    fireEvent.change(screen.getByLabelText("Permanent Account Number"), {
      target: { value: "ABCPE1234F" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify PAN" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(screen.getByRole("button", { name: "Retry" })).toBeVisible();
    expect(new Set([0, 1, 2, 3].map(keyAt)).size).toBe(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(4);
    fetchMock.mockResolvedValueOnce(reply(found));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(keyAt(4)).toBe(keyAt(0));
  });

  it("distinguishes network failures and safely retries the same attempt", async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(reply(found));
    render(<App />);
    await fill();
    await userEvent.click(screen.getByRole("button", { name: "Verify PAN" }));
    expect(await screen.findByText(/Connection interrupted/)).toBeVisible();
    expect(screen.queryByText("Not charged")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("RAHUL SHARMA")).toBeVisible();
    expect(keyAt(1)).toBe(keyAt(0));
  });

  it("works when browser storage is blocked", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    fetchMock.mockResolvedValue(reply(found));
    render(<App />);
    await fill();
    await userEvent.click(screen.getByRole("button", { name: "Verify PAN" }));
    expect(await screen.findByText("RAHUL SHARMA")).toBeVisible();
  });

  it("bounds saved history to twenty masked entries", async () => {
    localStorage.setItem(
      "idto.history",
      JSON.stringify(
        Array.from({ length: 25 }, () => ({
          pan: "ABCPE****F",
          outcome: "Found",
          time: "2026-11-13T08:00:00.000Z",
        })),
      ),
    );
    fetchMock.mockResolvedValue(reply(found));
    render(<App />);
    await fill();
    await userEvent.click(screen.getByRole("button", { name: "Verify PAN" }));
    await screen.findByText("RAHUL SHARMA");
    const entries: unknown[] = JSON.parse(
      localStorage.getItem("idto.history") ?? "[]",
    );
    expect(entries).toHaveLength(20);
    expect(JSON.stringify(entries)).not.toContain("ABCPE1234F");
  });

  it("ignores malformed storage", () => {
    localStorage.setItem("idto.history", "{broken");
    render(<App />);
    expect(screen.getByText("Your checks will appear here.")).toBeVisible();
  });
});
