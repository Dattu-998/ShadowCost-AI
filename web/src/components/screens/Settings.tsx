"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { Button, Empty, ErrorNote, fmt, Loading, Panel, Pill, Tabs, TitleRow } from "@/components/app/ui";
import {
  del,
  fetcher,
  patch,
  post,
  type Members,
  type Notification,
  type Plan,
  type Role,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";

/*
 * Settings. One screen, four tabs: the workspace's name, its team, its plan and the log of every
 * notification it sent. Owners and admins change things; everyone else can read.
 */

type Tab = "workspace" | "team" | "billing" | "notifications";
const TABS: { id: Tab; label: string }[] = [
  { id: "workspace", label: "Workspace" },
  { id: "team", label: "Team" },
  { id: "billing", label: "Plan and billing" },
  { id: "notifications", label: "Notifications" },
];
const ROLE_HELP: Record<Role, string> = {
  owner: "Everything, including billing",
  admin: "Data, agents and the team",
  approver: "Approves agents and their actions",
  viewer: "Reads everything, changes nothing",
};

function Message({ value }: { value: { tone: "good" | "bad"; text: string } | null }) {
  if (!value) return null;
  return (
    <p
      role={value.tone === "bad" ? "alert" : "status"}
      className={`mb-4 rounded-md px-3 py-2.5 text-[14px] ${value.tone === "bad" ? "bg-bad-tint text-bad" : "bg-good-tint text-good"}`}
    >
      {value.text}
    </p>
  );
}

function useAction() {
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  async function run(label: string, task: () => Promise<string | void>) {
    setBusy(label);
    setMessage(null);
    try {
      const text = await task();
      if (text) setMessage({ tone: "good", text });
    } catch (err) {
      setMessage({ tone: "bad", text: (err as Error).message });
    } finally {
      setBusy(null);
    }
  }
  return { busy, message, run };
}

function WorkspaceTab() {
  const { org, can } = useWorkspace();
  const { mutate } = useSWRConfig();
  const [name, setName] = useState<string | null>(null);
  const { busy, message, run } = useAction();
  if (!org) return <Loading />;
  const value = name ?? org.name;
  return (
    <Panel title="Workspace">
      <Message value={message} />
      <form
        className="max-w-md space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          run("rename", async () => {
            await patch(`/v1/orgs/${org.id}`, { name: value.trim() });
            await mutate(`/v1/orgs/${org.id}`);
            setName(null);
            return "Renamed.";
          });
        }}
      >
        <label className="block">
          <span className="text-[14px] font-semibold">Name</span>
          <input
            value={value}
            maxLength={80}
            disabled={!can("admin")}
            onChange={(e) => setName(e.target.value)}
            className="mt-1.5 h-9 w-full rounded-md border border-control px-3 text-[14px] outline-none focus:border-ink disabled:bg-hover"
          />
        </label>
        {can("admin") && (
          <Button type="submit" disabled={busy !== null || !value.trim() || value.trim() === org.name}>
            {busy ? "Saving…" : "Save"}
          </Button>
        )}
      </form>
      <dl className="mt-6 grid max-w-md grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-[14px]">
        <dt className="text-muted">Your role</dt>
        <dd className="capitalize">{org.role}</dd>
        <dt className="text-muted">Workspace ID</dt>
        <dd className="truncate font-mono text-[13px]">{org.id}</dd>
      </dl>
    </Panel>
  );
}

function TeamTab() {
  const { org, can, approver } = useWorkspace();
  const key = org ? `/v1/orgs/${org.id}/members` : null;
  const team = useSWR<Members>(key, fetcher);
  const { mutate } = useSWRConfig();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("approver");
  const [link, setLink] = useState<string | null>(null);
  const { busy, message, run } = useAction();
  if (!org) return <Loading />;
  const admin = can("admin");
  const refresh = async () => {
    await mutate(key);
    await mutate(`/v1/orgs/${org.id}`);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_384px]">
      <Panel
        title="Members"
        aside={
          <span className="text-[13px] text-muted">
            {org.usage.members} of {org.limits.members} seats on {org.plan_name}
          </span>
        }
      >
        <Message value={message} />
        {team.error ? (
          <ErrorNote error={team.error} retry={() => team.mutate()} />
        ) : !team.data ? (
          <Loading />
        ) : (
          <ul className="-my-3 divide-y divide-rule">
            {team.data.members.map((m) => (
              <li key={m.user_id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[14px] font-semibold">
                    {m.email}
                    {m.email === approver && <span className="ml-2 font-normal text-muted">you</span>}
                  </p>
                  <p className="text-[13px] text-muted">Joined {fmt.date(m.created_at)}</p>
                </div>
                {admin && m.role !== "owner" && m.email !== approver ? (
                  <>
                    <label>
                      <span className="sr-only">Role for {m.email}</span>
                      <select
                        value={m.role}
                        disabled={busy !== null}
                        onChange={(e) =>
                          run(`role-${m.user_id}`, async () => {
                            await patch(`/v1/orgs/${org.id}/members/${m.user_id}`, { role: e.target.value });
                            await refresh();
                            return `${m.email} is now ${e.target.value}.`;
                          })
                        }
                        className="h-8 rounded-md border border-control bg-sheet px-2 text-[13px] capitalize"
                      >
                        {(["admin", "approver", "viewer"] as const).map((r) => (
                          <option key={r} value={r}>
                            {r}
                          </option>
                        ))}
                      </select>
                    </label>
                    <Button
                      variant="quiet"
                      className="text-bad"
                      disabled={busy !== null}
                      onClick={() => {
                        if (!window.confirm(`Remove ${m.email} from ${org.name}?`)) return;
                        run(`remove-${m.user_id}`, async () => {
                          await del(`/v1/orgs/${org.id}/members/${m.user_id}`);
                          await refresh();
                          return `${m.email} was removed.`;
                        });
                      }}
                    >
                      Remove
                    </Button>
                  </>
                ) : (
                  <Pill>{m.role.charAt(0).toUpperCase() + m.role.slice(1)}</Pill>
                )}
              </li>
            ))}
            {team.data.invitations.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[14px]">{i.email}</p>
                  <p className="text-[13px] text-muted">
                    Invited as {i.role} · link expires {fmt.date(i.expires_at)}
                  </p>
                </div>
                <Pill tone="wait">Invited</Pill>
                {admin && (
                  <Button
                    variant="quiet"
                    disabled={busy !== null}
                    onClick={() =>
                      run(`revoke-${i.id}`, async () => {
                        await del(`/v1/orgs/${org.id}/invitations/${i.id}`);
                        await refresh();
                        return `The invitation to ${i.email} was withdrawn.`;
                      })
                    }
                  >
                    Withdraw
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <div className="space-y-4">
        {admin && (
          <Panel title="Invite someone">
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                setLink(null);
                run("invite", async () => {
                  const sent = await post<{ invite_url: string; emailed: boolean }>(
                    `/v1/orgs/${org.id}/invitations`,
                    { email: email.trim(), role },
                  );
                  await refresh();
                  setEmail("");
                  if (!sent.emailed) {
                    setLink(sent.invite_url);
                    return "Invitation created. Email isn't set up, so send them the link below.";
                  }
                  return "Invitation sent.";
                });
              }}
            >
              <label className="block">
                <span className="text-[14px] font-semibold">Email</span>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="mt-1.5 h-9 w-full rounded-md border border-control px-3 text-[14px] outline-none focus:border-ink"
                />
              </label>
              <fieldset>
                <legend className="text-[14px] font-semibold">Role</legend>
                <div className="mt-1.5 space-y-1.5">
                  {(["admin", "approver", "viewer"] as const).map((r) => (
                    <label key={r} className="flex items-start gap-2 text-[14px]">
                      <input
                        type="radio"
                        name="role"
                        value={r}
                        checked={role === r}
                        onChange={() => setRole(r)}
                        className="mt-1 accent-[#1f3527]"
                      />
                      <span>
                        <span className="capitalize">{r}</span>
                        <span className="block text-[13px] text-muted">{ROLE_HELP[r]}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <Button type="submit" disabled={busy !== null}>
                {busy === "invite" ? "Inviting…" : "Send invitation"}
              </Button>
            </form>
            {link && (
              <div className="mt-4">
                <label className="block">
                  <span className="text-[13px] text-muted">Invitation link, valid 7 days</span>
                  <input
                    readOnly
                    value={link}
                    onFocus={(e) => e.target.select()}
                    className="mt-1 h-9 w-full rounded-md border border-control bg-hover px-3 font-mono text-[12px]"
                  />
                </label>
                <Button variant="secondary" className="mt-2" onClick={() => navigator.clipboard?.writeText(link)}>
                  Copy link
                </Button>
              </div>
            )}
          </Panel>
        )}
        <Panel title="Roles">
          <dl className="space-y-2 text-[14px]">
            {(Object.keys(ROLE_HELP) as Role[]).map((r) => (
              <div key={r}>
                <dt className="font-semibold capitalize">{r}</dt>
                <dd className="text-muted">{ROLE_HELP[r]}</dd>
              </div>
            ))}
          </dl>
        </Panel>
      </div>
    </div>
  );
}

function BillingTab() {
  const { org, can } = useWorkspace();
  const params = useSearchParams();
  const plans = useSWR<Plan[]>("/v1/plans", fetcher);
  const { busy, message, run } = useAction();
  if (!org) return <Loading />;
  const owner = can("owner");
  const checkout = params.get("checkout");
  const go = (label: string, path: string, body?: unknown) =>
    run(label, async () => {
      const { url } = await post<{ url: string }>(path, body);
      window.location.assign(url);
    });

  const limit = (n: number | null) => (n === null ? "Unlimited" : fmt.num(n));
  return (
    <div className="space-y-6">
      {checkout === "success" && (
        <Message value={{ tone: "good", text: "Thanks. Your plan updates as soon as Stripe confirms the payment, usually within seconds." }} />
      )}
      {checkout === "cancelled" && <Message value={{ tone: "bad", text: "Checkout was cancelled; nothing was charged." }} />}
      <Message value={message} />
      <Panel
        title="Current plan"
        aside={
          owner && org.plan !== "free" && org.features.billing ? (
            <Button variant="secondary" disabled={busy !== null} onClick={() => go("portal", `/v1/orgs/${org.id}/billing/portal`)}>
              {busy === "portal" ? "Opening…" : "Manage billing"}
            </Button>
          ) : null
        }
      >
        <p className="text-[24px] font-semibold tracking-tight">{org.plan_name}</p>
        <p className="mt-1 text-[14px] text-muted">
          {org.subscription_status
            ? `Subscription ${org.subscription_status.replace("_", " ")}${org.current_period_end ? `, renews ${fmt.date(org.current_period_end)}` : ""}`
            : "No subscription"}
        </p>
        <dl className="mt-5 grid grid-cols-3 gap-4 text-[14px] sm:max-w-lg">
          {(
            [
              ["Seats", org.usage.members, org.limits.members],
              ["Datasets", org.usage.datasets, org.limits.datasets],
              ["Approved agents", org.usage.approved_agents, org.limits.approved_agents],
            ] as const
          ).map(([label, used, max]) => (
            <div key={label}>
              <dt className="text-muted">{label}</dt>
              <dd className="tabular mt-0.5 font-semibold">
                {used} of {limit(max)}
              </dd>
            </div>
          ))}
        </dl>
      </Panel>

      {plans.error ? (
        <ErrorNote error={plans.error} retry={() => plans.mutate()} />
      ) : !plans.data ? (
        <Loading />
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          {plans.data.map((p) => {
            const current = p.id === org.plan;
            return (
              <section
                key={p.id}
                className={`flex flex-col rounded-[10px] border bg-sheet p-5 ${current ? "border-ink" : "border-edge"}`}
              >
                <h3 className="text-[15px] font-semibold">{p.name}</h3>
                <p className="mt-2">
                  <span className="text-[26px] font-semibold tracking-tight">${p.monthly_usd}</span>
                  <span className="text-[14px] text-muted"> a month</span>
                </p>
                <p className="mt-2 text-[14px] text-muted">{p.blurb}</p>
                <ul className="mt-4 space-y-1 text-[14px]">
                  <li>{p.members === 1 ? "1 seat" : `${p.members} seats`}</li>
                  <li>{p.datasets} datasets</li>
                  <li>{p.approved_agents === null ? "Unlimited agents" : `${p.approved_agents} approved agent${p.approved_agents === 1 ? "" : "s"}`}</li>
                  <li>{p.connectors ? "Google Sheets and Gmail" : "File uploads only"}</li>
                </ul>
                <div className="mt-auto pt-5">
                  {current ? (
                    <Pill tone="good">Your plan</Pill>
                  ) : !org.features.billing ? (
                    <p className="text-[13px] text-muted">Payments aren&apos;t configured on this server yet.</p>
                  ) : p.id === "free" ? (
                    owner && <p className="text-[13px] text-muted">Cancel from Manage billing to return to Free.</p>
                  ) : owner ? (
                    org.plan === "free" ? (
                      <Button
                        disabled={busy !== null}
                        onClick={() => go(`plan-${p.id}`, `/v1/orgs/${org.id}/billing/checkout`, { plan: p.id })}
                      >
                        {busy === `plan-${p.id}` ? "Opening checkout…" : `Upgrade to ${p.name}`}
                      </Button>
                    ) : (
                      <Button variant="secondary" disabled={busy !== null} onClick={() => go("portal", `/v1/orgs/${org.id}/billing/portal`)}>
                        Switch in Manage billing
                      </Button>
                    )
                  ) : (
                    <p className="text-[13px] text-muted">The workspace owner changes plans.</p>
                  )}
                </div>
              </section>
            );
          })}
        </div>
      )}
      {org.features.billing && (
        <p className="text-[13px] text-muted">
          Payments run on Stripe in test mode: use card 4242 4242 4242 4242, any future date and any CVC.
        </p>
      )}
    </div>
  );
}

function NotificationsTab() {
  const { org } = useWorkspace();
  const log = useSWR<Notification[]>(org ? `/v1/orgs/${org.id}/notifications` : null, fetcher);
  return (
    <Panel title="Sent notifications">
      <p className="-mt-1 mb-4 text-[14px] text-muted">
        Approvers are emailed when an agent is promoted or demoted and when actions wait for a decision.
      </p>
      {log.error ? (
        <ErrorNote error={log.error} retry={() => log.mutate()} />
      ) : !log.data ? (
        <Loading />
      ) : log.data.length === 0 ? (
        <Empty>Nothing sent yet.</Empty>
      ) : (
        <ul className="-my-3 divide-y divide-rule">
          {log.data.map((n) => (
            <li key={n.id} className="flex flex-wrap items-start gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-[14px] font-semibold">{n.subject}</p>
                <p className="truncate text-[13px] text-muted">
                  To {n.recipients.join(", ") || "nobody"} · {fmt.date(n.created_at)}
                </p>
              </div>
              <Pill tone={n.delivered ? "good" : "neutral"}>{n.delivered ? "Emailed" : "Logged only"}</Pill>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function SettingsScreen() {
  const params = useSearchParams();
  const router = useRouter();
  const requested = params.get("tab") as Tab | null;
  const tab: Tab = TABS.some((t) => t.id === requested) ? requested! : "workspace";
  return (
    <div className="space-y-6">
      <TitleRow title="Settings" line="Your workspace, its team and its plan." />
      <Tabs label="Settings" items={TABS} value={tab} onChange={(id) => router.replace(`/app/settings?tab=${id}`)} />
      {tab === "workspace" && <WorkspaceTab />}
      {tab === "team" && <TeamTab />}
      {tab === "billing" && <BillingTab />}
      {tab === "notifications" && <NotificationsTab />}
    </div>
  );
}

export default function Settings() {
  return (
    <Suspense fallback={<Loading />}>
      <SettingsScreen />
    </Suspense>
  );
}
