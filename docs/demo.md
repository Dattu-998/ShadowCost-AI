# Demo video script (about 3 minutes)

Record the deployed app (or `streamlit run app/streamlit_app.py`) at 1280×720.
Before recording, delete `workspace/` so no agents are approved yet.

| Time | Screen | Say |
|---|---|---|
| 0:00 | Overview tab, sample data | "Small companies run on spreadsheets and email. ShadowCost finds the repetitive parts and automates them, but only after each agent proves itself against what the person actually did." |
| 0:15 | Point at files and events metrics | "Here's four months of a simulated wholesaler: daily copies of the invoice sheet, a bank export and the mailbox. No event logs, no process-mining setup." |
| 0:30 | **1 Discover** tab; open W3 | "It found three repeated workflows and what triggers them. For chasing, it recovered the actual rule, Mondays and Thursdays, at least 7 days past due, unpaid, from the data alone. Every time estimate lists its assumptions." |
| 0:55 | **2 Agents** tab; expand W2's rules | "An LLM drafted an agent for each one, as data, not code. A deterministic engine runs it and a whitelist stops the spec from running anything else. Each draft was tested on 40 days it never saw: 100%, 78%, 78% agreement, the same as rules written by hand from the simulator." |
| 1:25 | Type a name, click **Approve** on W1 and W2 | "Nothing runs until a person approves it, and editing a spec voids the approval." |
| 1:35 | Sidebar: switch to **Simulated year**; **3 Shadow mode** | "Over a year in shadow mode, the invoice agent climbs from shadow to draft to approval to autonomous, 30 cases at a time with a 95% confidence bound. The payment agent gets there by July. The chasing agent stays in shadow, which is correct: chasing needs judgment." |
| 2:10 | **4 Execute**: W2, a day in May, stage Approval, Run | "At the approval stage, actions wait in a queue. At draft stage you get email drafts; when autonomous, it writes to an outbox and a new copy of the sheet. It never sends or overwrites anything directly." |
| 2:30 | **5 Report**: Build report, scroll to Savings | "The report gives savings both ways: 41 hours estimated from stated assumptions, 48 measured from the person's actual minutes." |
| 2:45 | GitHub README | "It's all open source, with tests, method write-ups and an honest list of what it can't do yet." |

Upload the video (YouTube unlisted or Loom) and link it at the top of the README.
