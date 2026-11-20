# Money on the board — what to build, and what Alfred must not say

Research for the finance track, written 2026-11-20 from the owner's brief:
log income and outgoings with mechanics matching **Money Manager** (Realbyte),
let Alfred see the picture, and let him do the planning arithmetic — a car, a
wedding, "what can we do with what we have".

This file stands to the finance work as
`Human behaviour science for Alfred.md` stands to the habit work: it is the
source of truth, and `services/alfred_principles.py` must not acquire a
financial claim this document does not support.

---

## 1. The parity target, as it actually behaves

Money Manager's reputation rests on a small, strict model. The mechanics worth
copying, verified against Realbyte's own help pages and the store listings
rather than from memory:

| Mechanic | How it actually works |
|---|---|
| **Double entry** | The app describes itself as applying a double-entry bookkeeping system. Every record — income, expense or transfer — *moves money between accounts*. Nothing is a bare number with a label. |
| **Three record types** | Income, Expense, Transfer. There is no fourth. |
| **Transfer is load-bearing** | Transfers between your own accounts are deliberately **excluded** from the income/expense tabs. A cash withdrawal is a transfer. **A credit-card payment is a transfer** from the bank account to the card — not an expense. Realbyte state this explicitly. |
| **Accounts, grouped** | Cash, bank accounts, cards, savings, investments, overdrafts, loans, insurance, other. Asset tracking across savings, insurance, loans and real estate rides on the same double-entry booking. |
| **Categories, two trees** | Separate main/sub category trees for income and for expense. Presets shipped, all editable, user categories addable. |
| **Budgets per category** | A monthly budget per category, with weekly and annual periods also available, and a graph of spend against it. |
| **Cards have a settlement date** | Setting it is what produces "payable" versus "outstanding" for each card. |
| **Recurring records** | Repeating transactions and automatic transfers between accounts, with a configurable frequency. |
| **Period start day** | The budget month need not start on the 1st. |
| **Reports** | Pie by category, bars by month, a calendar with daily totals, budget-versus-actual. |
| **Export** | Excel out, and a PC/Wi-Fi editing path. |
| **Five views on one month** | Daily (the record, grouped by day), Calendar (a month grid with income, expense and net per day), Monthly (the year, each month split into its weeks), Summary (where the money sits, plus the budget bar), Description (notes). The three figures — Income, Exp., Total — sit above all five and never move. |
| **Stats, separately** | A pie by category with a ranked list underneath, an Income/Expense toggle, and a period selector offering Weekly, Monthly, Annually, Period, List and Trend. |
| **Notes are data** | A note on a record ("Taxi", "Abed") is aggregated in its own view, counted and totalled — so the free-text field is a reporting dimension, not a scribble. |
| **A transfer carries a fee** | The transfer form has its own Fees control beside the amount. |
| **Entry is a calculator** | The amount field opens a keypad with + − × ÷ and =, because real amounts are often a sum of several. |

**Carry-over exists, contrary to what the reviews say.** The web write-ups
describe it as a frequently requested missing feature; the app's own Settings
screen lists *Monthly Start Date, Carry-over Setting, Period* together under
**Transaction Settings**. Parity therefore includes it: unspent budget rolling
into the next period, as a setting rather than a default. This is the clearest
case in this document for trusting a screenshot of the running app over any
amount of secondary writing about it.

The free tier's caps (10 accounts, 5 budgets, 5 goals) are a business model,
not a mechanic. Copy none of them.

---

## 2. Five decisions that must be right in the first migration

Everything else in the finance track can be changed later. These cannot, because
they are baked into the shape of the stored rows.

**1. Money is an integer count of minor units. Never a float.**
`amount_minor INTEGER` plus a currency code, so 45 000 UZS is `4500000` tiyin
and $12.99 is `1299` cents. Floating point cannot represent `0.10`; a ledger
built on `Float` drifts, and the drift shows up as a balance that is wrong by a
few units and cannot be explained to the person. The exponent is per currency
(UZS has no practical minor unit in daily use, USD has two), so the currency's
exponent must be stored or derived — not assumed to be 2.

**2. One function owns the posting invariant.**
This codebase already has the pattern and the scar tissue to justify it:
`mission_service.resolve_placement` is the single home of the
section-belongs-to-its-list rule. Finance needs the identical treatment, because
the three record types each constrain the row differently:

- **expense** — `from_account` required, `to_account` NULL, category must be an *expense* category
- **income** — `to_account` required, `from_account` NULL, category must be an *income* category
- **transfer** — both accounts required and **distinct**, category NULL

Scattering those checks between a router, an Alfred tool and an importer
guarantees the three will disagree, and a ledger that disagrees with itself is
worse than no ledger. One resolver, called by every writer.

**3. Currency is first-class, and the rate is stored on the row.**
Accounts carry a currency; the user has a main currency for reporting. A
transaction stores its amount in its account's currency **and the rate used at
the time**. Re-deriving historical totals from today's rate means last year's
spending changes every time the exchange rate moves — the report becomes
unfalsifiable and the projection built on it is fiction. Nothing here may assume
which currency anyone uses: per rule 1, main currency is a per-user field with
no default baked into the code.

**4. The period start day is a setting, not the 1st.**
Salary dates, not calendar months, are what make a budget match a life. Every
aggregate — budget, report, projection — must take its window from the user's
period start day and their timezone, through `services/timezones.py`. Naive
"this month" is the same bug as naive "today", which this project has already
been bitten by.

**5. Recurring records fire exactly once.**
This is solved here already: insert-first into a `*_log` table with a UNIQUE
constraint, driven by `POST /api/internal/cron/tick`, safe under repeated runs
and multiple workers. A recurring salary that posts twice because two workers
ticked at once is a corrupted ledger, and the person's first clue is a balance
they cannot explain. Reuse the pattern, do not invent a second one.

---

## 3. The consulting half: what the evidence actually supports

The brief asks for financial planning and projection. The honest state of the
evidence is narrower than the genre's confidence suggests, and the gap matters
because it decides what Alfred may assert.

**Budgeting and mental accounting: associated with better outcomes, not shown to
cause them.** The literature on mental budgeting is overwhelmingly
cross-sectional. Surveys link mental budgeting to better self-reported financial
management and higher financial well-being
([PMC10645357](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10645357/);
[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0167487011000596)),
but these are associations. The findings are not even uniform: Zhang and Sussman
(2018) found no effect of mental accounting on financial management, while other
work finds it cuts the other way and is linked to *consumptive* behaviour, or
produces under- and over-consumption through rigid category walls
([Springer 2026](https://link.springer.com/article/10.1007/s44202-026-00709-4)).
The strongest causal-looking evidence is observational: an NBER working paper
documents households managing non-fungible budgets through separate payment
cards, where funds arriving on one card raised total spending without an
offsetting cut elsewhere
([NBER w31613](https://www.nber.org/system/files/working_papers/w31613.pdf)).

The product consequence is specific. **Categories are a reporting device, not a
treatment.** Shipping them is right — they are how a person reads their own
behaviour — but the app may not claim that categorising spending improves it.

**Reminders work, and then stop working.** This is the best-evidenced
intervention in the set, and it comes with a built-in expiry. Reminders increase
savings balances and deposit counts
([Karlan et al.](https://poverty-action.org/sites/default/files/publications/getting-to-the-top-of-mind.pdf)),
but a Paraguay SMS trial found the effect present during the messaging period
and **fading once messaging stopped**
([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0167268124001409)).
That is an argument for finance nudges inside the existing nudge budget and
quiet hours — and an argument against believing a streak of messages is doing
lasting work.

**Commitment devices: mixed, and the better ones are structural.** A portable
savings device in urban India raised total savings ~19% at six months, holding up
at twenty months in a subsample
([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0167268121004984)).
Against that, the wider commitment-device literature shows small short-term
effects that often do not persist
([overview](https://en.wikipedia.org/wiki/Commitment_device)), and a Malawi
default-savings trial found no change in temptation spending. A meta-analysis of
13 RCTs covers making basic savings accounts easier to reach
([CGD](https://www.cgdev.org/sites/default/files/meta-analysis-savings-deposit-take-up-utilization.pdf)).
Notably, "Save More Tomorrow"-style automatic enrolment works through inertia
and defaults rather than binding constraint — it is a nudge, not a commitment.

**What this means for a savings goal feature:** a goal is worth building because
it makes the arithmetic visible and gives the money a name. It is not worth
claiming it will make someone save. The defensible promise is *clarity*, and
clarity is enough.

**The gap, stated plainly:** no randomised evidence was found on budgeting *apps*
as an intervention. Everything above is adjacent. A finance module in a life
companion is a reasonable thing to build and an unproven thing to prescribe.

---

## 4. Financial folklore Alfred must never repeat

The same treatment as the habit myths in rule 4, and for the same reason:
repeating these would make him confidently wrong about somebody's money.

- **"50/30/20"** — needs/wants/savings. A rule of thumb from a trade book, never
  a finding, and arithmetically impossible on many real incomes. Quoting it to
  someone whose rent is 60% of take-home is an insult dressed as advice.
- **"The latte factor"** — that small discretionary purchases are what stand
  between a person and wealth. It is a rhetorical device; the arithmetic is
  dominated by income, housing and large irregulars, which is what the app can
  actually show.
- **"Six months of expenses"** as the universal emergency fund. The right buffer
  depends on income volatility, dependants and what a bad month actually costs —
  all of which are in the user's own data. Compute it, never recite it.
- **"Pay yourself first"** as a law rather than one ordering among several.
- **"Snowball beats avalanche"** (or the reverse) as settled. Highest-interest-
  first is arithmetically cheaper; smallest-balance-first is argued to sustain
  motivation; the comparative evidence is mixed. This is the user's judgement
  call, and Alfred's job is to show both numbers, not to pick.
- **Any return assumption.** "Say 7% a year" turns a projection into a promise.
  Projections use the user's own observed numbers or they are not made.
- **Any claim that spending reveals a psychological state.** The same bar as
  burnout: describe the pattern, never diagnose the person. "Dining out tripled
  in October" is his. "You were stress-spending" is not.

---

## 5. Where Alfred must step back

The existing honesty floor already forbids him pretending to a body or
diagnosing a mind. Money adds a third boundary, and it is a bright line:

**Alfred does arithmetic on the user's own numbers. He does not advise on
products, markets or instruments.**

In scope, and genuinely useful:

- "Your median monthly surplus over the last six complete months is X."
- "At that surplus, 18 000 USD is fourteen months away — June 2028."
- "To reach it by next August you would need Y a month. You have cleared that
  in one of the last six months."
- "This recurring commitment takes your projected balance negative in March."

Out of scope, permanently: which account to open, which fund, which currency to
hold, whether to buy or rent, whether a loan is a good idea, what the som or the
dollar will do. He is not licensed, not informed about the user's full
circumstances, and the overtrust evidence in the behaviour report applies with
extra force here — anthropomorphic systems amplify deference, and a confident
butler is the ideal vehicle for a costly mistake. When asked, he should say he is
not the right source and that this one deserves a person, in the same register he
already uses for being out of his depth.

He must also carry the existing hedge at claim level: **he sees what is logged
and nothing else.** A projection from four logged months is a projection from
four logged months, and it must say so — with a range, and the number of periods
it rests on, not a single confident figure. The house precedent is
`focus_service.suggested_focus_minutes`: the user's own median, never a
constant. Medians, not means — one hospital bill or one bonus destroys a mean,
and the person then disbelieves the whole report, correctly.

---

## 6. Two rules this track adds to the project

**Money earns no Bat Points.** Exactly the work-track boundary, for a sharper
reason. Paying points for logging a transaction incentivises logging over
accuracy; paying them for spending or saving gamifies money, and the behaviour
report's commitment against variable or engagement-driven reward applies
directly. Points are written in exactly three services — mission, habit and
focus. Finance must not become a fourth, and a test should assert it.

**Finance is the most sensitive data in the app, and must be switchable off.**
Follow `work_enabled` precisely: tri-state, NULL resolving to "on if they already
have finance data", destroying nothing when switched off, and off meaning off
everywhere. Beyond that, Alfred's context reaches an LLM provider that may be a
third party under the user's own key, so the default should be that **he sees
aggregates, not rows** — totals, category sums, balances and surplus, rather
than every merchant and amount — with a per-user setting for anyone who wants
him to see more. Rule 5 keeps API keys out of logs and responses; the same
instinct applies to a person's ledger.

---

## 7. The thing that decides whether any of this gets used

A finance tracker dies of entry friction. Money Manager's real feature is that a
record takes three taps.

bat-board's advantage is that it already has the better answer: **Alfred on
Telegram.** "spent 45k on lunch" typed or spoken in passing, parsed into an
expense against the right account and category, is lower friction than any form —
and recurring records remove the predictable half of the logging entirely. That
is why natural-language capture belongs immediately after the ledger exists,
rather than at the end as a convenience. Everything else here — budgets,
reports, projections, plans — is arithmetic on a ledger, and the ledger only
exists if logging costs nothing.

---

## Sources

Money Manager mechanics: [Realbyte: how to record a transfer](https://help.realbyteapps.com/hc/en-us/articles/360042842254-How-to-record-a-transfer),
[Realbyte](https://www.realbyteapps.com/),
[App Store listing](https://apps.apple.com/us/app/money-manager-expense-budget/id560481810),
[Google Play listing](https://play.google.com/store/apps/details?id=com.realbyteapps.moneymanagerfree&hl=en_US),
[review, 2026](https://www.laya.finance/guides/money-manager-app-review),
[feature comparison](https://productivity-apps.com/apps/compare/money-manager-expense-budget-vs-wallet-by-budgetbakers).

Evidence: [NBER w31613 — mental accounts and payment cards](https://www.nber.org/system/files/working_papers/w31613.pdf),
[mental budgeting and household finance](https://www.sciencedirect.com/science/article/abs/pii/S0167487011000596),
[financial literacy, mental budgeting, self-control](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10645357/),
[mental accounting and consumptive behaviour](https://link.springer.com/article/10.1007/s44202-026-00709-4),
[Karlan et al. — reminders increase saving](https://poverty-action.org/sites/default/files/publications/getting-to-the-top-of-mind.pdf),
[personalising or reminding — effects fade](https://www.sciencedirect.com/science/article/abs/pii/S0167268124001409),
[portable savings device, urban India](https://www.sciencedirect.com/science/article/abs/pii/S0167268121004984),
[CGD meta-analysis of 13 savings RCTs](https://www.cgdev.org/sites/default/files/meta-analysis-savings-deposit-take-up-utilization.pdf),
[commitment devices overview](https://en.wikipedia.org/wiki/Commitment_device).
