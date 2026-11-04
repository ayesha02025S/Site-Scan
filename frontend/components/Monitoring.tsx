"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Bell,
  Check,
  Globe2,
  LoaderCircle,
  Pause,
  Play,
  Radar,
  Trash2,
} from "lucide-react";

import type { AppNotification, Monitor, Scan } from "../lib/results";

const dateLabel = (date: string) =>
  new Date(date).toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

type Props = {
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
  notifications: AppNotification[];
  onReadAll: () => void;
  onOpenScan: (scanId: string) => void;
  onScanStarted: () => void;
};

export default function Monitoring({
  request,
  notifications,
  onReadAll,
  onOpenScan,
  onScanStarted,
}: Props) {
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [url, setUrl] = useState("");
  const [frequency, setFrequency] = useState<Monitor["frequency"]>("daily");
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const unread = notifications.some((item) => !item.read);

  async function attempt(action: () => Promise<void>) {
    setError("");
    try {
      await action();
    } catch (exc) {
      setError((exc as Error).message);
    }
  }

  useEffect(() => {
    let live = true;
    let fetching = false;
    async function load() {
      if (fetching) return;
      fetching = true;
      try {
        const list = await request<Monitor[]>("/monitors");
        if (live) setMonitors(list);
      } catch (exc) {
        if (live) setError((exc as Error).message);
      } finally {
        fetching = false;
        if (live) setLoading(false);
      }
    }
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, []);

  async function add(event: FormEvent) {
    event.preventDefault();
    if (!url.trim() || saving) return;
    setSaving(true);
    await attempt(async () => {
      const created = await request<Monitor>("/monitors", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), frequency }),
      });
      setMonitors((items) => [created, ...items]);
      setUrl("");
      onScanStarted();
    });
    setSaving(false);
  }

  async function scanNow(monitor: Monitor) {
    if (starting || monitor.active_scan_id) return;
    setStarting(monitor.id);
    setNotice("");
    await attempt(async () => {
      const scan = await request<Scan>(`/monitors/${monitor.id}/scan`, {
        method: "POST",
      });
      setMonitors((items) =>
        items.map((item) =>
          item.id === monitor.id ? { ...item, active_scan_id: scan.id } : item,
        ),
      );
      setNotice(
        "Scan queued. Your schedule is unchanged. Results will appear in Scan history.",
      );
      onScanStarted();
    });
    setStarting(null);
  }

  function toggle(monitor: Monitor) {
    void attempt(async () => {
      const updated = await request<Monitor>(`/monitors/${monitor.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: !monitor.active }),
      });
      setMonitors((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
    });
  }

  function remove(monitor: Monitor) {
    void attempt(async () => {
      await request(`/monitors/${monitor.id}`, { method: "DELETE" });
      setMonitors((items) => items.filter((item) => item.id !== monitor.id));
    });
  }

  return (
    <>
      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
        </div>
      )}
      {notice && (
        <p role="status" className="monitor-note">
          {notice}
        </p>
      )}
      <section className="scan-panel panel">
        <div className="scan-panel-top">
          <div>
            <Radar size={16} />
            <h2>Monitor a website</h2>
          </div>
          <span className="tag">UP TO 5 SITES</span>
        </div>
        <form onSubmit={add}>
          <label htmlFor="monitor-url" className="sr-only">
            Website URL to monitor
          </label>
          <div className="url-input">
            <Globe2 size={18} />
            <input
              id="monitor-url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://example.com"
              required
              maxLength={2048}
              autoComplete="url"
              spellCheck={false}
            />
          </div>
          <label htmlFor="monitor-frequency" className="sr-only">
            Scan frequency
          </label>
          <select
            id="monitor-frequency"
            className="frequency-select"
            value={frequency}
            onChange={(event) =>
              setFrequency(event.target.value as Monitor["frequency"])
            }
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
          </select>
          <button className="button primary" type="submit" disabled={saving}>
            {saving ? <LoaderCircle size={16} className="spin" /> : null}
            Start monitoring
            <ArrowRight size={16} />
          </button>
        </form>
        <p className="monitor-note">
          The first scan starts now as a baseline. You are alerted when a later
          scan finds new issues or a site fails twice in a row.
        </p>
      </section>

      <section className="history panel monitoring-section">
        <div className="section-heading">
          <span className="section-number">01</span>
          <h2>Monitored websites</h2>
          <span className="count-badge">{monitors.length}</span>
        </div>
        {monitors.map((monitor) => (
          <div className="monitor-row" key={monitor.id}>
            <div className="monitor-target">
              <strong>{monitor.url}</strong>
              <small>
                {monitor.active
                  ? `${monitor.frequency} · next scan ${dateLabel(monitor.next_run_at)}`
                  : `${monitor.frequency} · paused`}
                {" · "}
                {monitor.email_enabled
                  ? `alerts also emailed to ${monitor.email}`
                  : "in-app alerts only"}
              </small>
            </div>
            <button
              className="text-button"
              disabled={starting !== null || !!monitor.active_scan_id}
              onClick={() => void scanNow(monitor)}
              aria-label={`Scan now ${monitor.url}`}
            >
              {starting === monitor.id || monitor.active_scan_id ? (
                <LoaderCircle size={13} className="spin" />
              ) : (
                <Radar size={13} />
              )}
              {starting === monitor.id || monitor.active_scan_id
                ? "Scanning…"
                : "Scan now"}
            </button>
            <button
              className="text-button"
              onClick={() => toggle(monitor)}
              aria-label={`${monitor.active ? "Pause" : "Resume"} monitoring ${monitor.url}`}
            >
              {monitor.active ? <Pause size={13} /> : <Play size={13} />}
              {monitor.active ? "Pause" : "Resume"}
            </button>
            <button
              className="text-button"
              onClick={() => remove(monitor)}
              aria-label={`Stop monitoring ${monitor.url}`}
            >
              <Trash2 size={13} />
              Remove
            </button>
          </div>
        ))}
        {!loading && !monitors.length && (
          <div className="no-findings">
            Add a website above to scan it automatically.
          </div>
        )}
      </section>

      <section className="history panel monitoring-section">
        <div className="section-heading">
          <span className="section-number">02</span>
          <h2>Alerts</h2>
          <span className="count-badge">{notifications.length}</span>
          {unread && (
            <button className="text-button" onClick={onReadAll}>
              <Check size={13} />
              Mark all read
            </button>
          )}
        </div>
        {notifications.map((item) => (
          <button
            className={`alert-row ${item.read ? "" : "unread"}`}
            key={item.id}
            onClick={() => onOpenScan(item.scan_id)}
          >
            <Bell size={15} />
            <span>
              <strong>{item.title}</strong>
              <small className="alert-body">{item.body}</small>
              <small>{dateLabel(item.created_at)}</small>
            </span>
            <ArrowUpRight size={15} />
          </button>
        ))}
        {!notifications.length && (
          <div className="no-findings">No alerts yet.</div>
        )}
      </section>
    </>
  );
}
