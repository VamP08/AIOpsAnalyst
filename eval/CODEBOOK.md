# Annotation codebook

Ground truth for the triage evaluation. Anyone should be able to reproduce the
labels from this document alone, and to check the ones that exist.

## Why this document exists

An LLM that sorts events into categories is easy to build and impossible to
trust without a measurement. The measurement is only as good as the labels it is
measured against, so the labels need the same treatment as code: a written
procedure, a record of who applied it, and the numbers published whatever they
say.

## Two sources of ground truth

**1. Maintainer labels (external).** Issues ingested from public repositories
arrive carrying labels applied by those projects' own maintainers: bug,
kind/feature, Feature request. Nobody on this project chose them, and anyone can
open the issue and verify. They are the primary ground truth.

Maintainer vocabularies do not separate "the process died" from "an operation
failed", so this comparison runs on a collapsed taxonomy:

| Maintainer label | Collapsed class |
|---|---|
| bug, kind/bug, type/bug, c-bug, bug report | defect (crash or error) |
| feature request, kind/feature, enhancement, feature | feature_request |
| question, kind/support, support | question |
| performance, kind/performance, perf | performance |

A cluster whose issues carry labels from two different classes is excluded
rather than guessed at. The mapping lives in
eval/harvest_maintainer_labels.py so it is auditable, not folklore.

**2. Author labels (internal).** Log clusters have no external labels, so they
are annotated by the repository author against this codebook, blind to the
model's verdicts. The author is not a systems administrator: the reference
section below supplies the domain knowledge, the decision procedure supplies the
rule, and ambiguous clusters are skipped rather than forced. Reported as what it
is - single-annotator labels made against a written codebook.

## Taxonomy

Six categories. A cluster gets exactly one.

| Category | Means | Does not mean |
|---|---|---|
| crash | a process or service died, exited unexpectedly, or failed to start | a single request failing while the service keeps serving |
| error | an operation failed; the service itself is alive | routine refusals that the configuration is supposed to produce |
| performance | slow, timing out, queueing, or exhausting a resource | a request to make something faster |
| feature_request | asks for behaviour that does not exist yet | a report that existing behaviour is broken |
| question | asks for help, how-to, or information | a report that includes a question in passing |
| noise | routine operation with nothing to act on | anything a responder would want to see |

## Decision procedure

Ask in this order and stop at the first yes.

1. Did something **die or fail to start**? -> crash
2. Does it ask for **behaviour that does not exist**? -> feature_request
3. Does it ask for **help or information**? -> question
4. Is it **slow, timing out, or out of a resource**? -> performance
5. Did an **operation fail** while the service stayed up? -> error
6. Otherwise -> noise

Label what the events are operationally, not what they might imply. A
brute-force SSH storm is thousands of failed operations -> error; "attack" is
not a category, and volume is severity's job.

## Boundary rules

- **Severity does not leak into category.** 690 failed logins is still error.
  How alarming it is gets recorded separately.
- **Report vs request.** "Training is 3x slower since v5" is performance;
  "please make training faster" is feature_request.
- **Config doing its job is noise.** A directory listing refused by rule, a
  request for a path that does not exist - the server behaved correctly. That is
  noise, even though an HTTP error code was returned. The distinction that
  matters: would a responder act on it?
- **Startup and shutdown chatter is noise** unless it reports a failure.
- **Skipping is data.** A cluster that resists the procedure after ~20 seconds
  is skipped and counted; a forced label is worse than a missing one, and a
  pattern of skips is feedback about the taxonomy.

## Reference: what these log lines are

Entries describe the mechanism and the operational consequence. They deliberately
do not state a category - that is the annotator's call through the decision
procedure above.

### OpenSSH (auth log)

| Template | What it is |
|---|---|
| Failed password for X from IP port N ssh2 | password authentication failed for an account that exists. One line per attempt. |
| Failed password for invalid user X from IP | same, for an account that does not exist - characteristic of automated guessing. |
| pam_unix(sshd:auth): authentication failure; logname= uid=0 ... | the same failure reported by the PAM stack rather than by sshd. Pairs with the lines above. |
| pam_unix(sshd:auth): check pass; user unknown | PAM looked up the account and found nothing. |
| Invalid user X from IP | sshd rejecting a login for a nonexistent account. |
| input_userauth_request: invalid user X [preauth] | the client asked to authenticate as an account that does not exist, before any credential was checked. |
| Received disconnect from IP 11: Bye Bye [preauth] | the client hung up before finishing authentication (disconnect code 11 = by application). Scanners do this constantly. |
| Connection closed by IP [preauth] | connection dropped before authentication completed. |
| Did not receive identification string from IP | something opened a TCP connection and never sent an SSH banner - a port scan or health probe. |
| error: Received disconnect from IP: 14: No more user authentication methods available | the client exhausted the auth methods it was willing to try and gave up. |
| Disconnecting: Too many authentication failures for X [preauth] | sshd cut the connection after the attempt limit (MaxAuthTries) was exceeded. |
| PAM service(sshd) ignoring max retries; 6 > 3 | the PAM stack was asked for more attempts than MaxAuthTries permits, so sshd capped it. Appears when something is hammering the login. |
| reverse mapping checking getaddrinfo for HOST IP failed - POSSIBLE BREAK-IN ATTEMPT! | the client's reverse DNS does not match its forward DNS. The wording is sshd's, and the usual cause is a badly configured PTR record rather than an intrusion. |
| message repeated 5 times: [ Failed password for root ... ] | syslog collapsing identical consecutive lines. The content is the repeated line. |

### Apache httpd (error log)

| Template | What it is |
|---|---|
| File does not exist: PATH | a request arrived for a path with no file behind it; the server answered 404. In these logs the paths are scanner probes (/phpgroupware, /bin). |
| script not found or unable to stat: PATH | same, for a CGI script path. |
| Directory index forbidden by rule: /var/www/html/ | directory listing requested where configuration forbids it; the server answered 403 as instructed. |
| attempt to invoke directory as script: /var/www/cgi-bin/ | a request tried to execute a directory as a CGI program; refused. |
| Invalid URI in request GET HTTP/1.1 | the request line was malformed. |
| request failed: error reading the headers | the client sent truncated or malformed headers. |
| request failed: URI too long (longer than 8190) | the request line exceeded the configured limit; refused. |
| Apache/2.0.49 (Fedora) configured -- resuming normal operations | startup finished; the server is serving. |
| Graceful restart requested, doing restart | an administrator or log-rotation script asked for a restart; existing connections are allowed to drain. |
| child process N still did not exit, sending a SIGTERM | during shutdown a worker ignored the polite signal and was terminated. Routine during restarts; persistent cases mean a stuck worker. |
| LDAP: Built with OpenLDAP LDAP SDK / LDAP: SSL support unavailable | startup notices about what the LDAP module was compiled with. |
| Digest: done / Digest: generating secret for digest authentication | digest-auth module initialising. |
| mod_python: Creating 32 session mutexes based on 150 max processes | module initialising and sizing its locks. |
| mod_security/1.9dev2 configured | module loaded at startup. |
| suEXEC mechanism enabled (wrapper: /usr/sbin/suexec) | startup notice: CGI programs will run under their owner's identity. |

### Apache with the Tomcat connector (mod_jk / mod_jk2)

| Template | What it is |
|---|---|
| workerEnv.init() ok /etc/httpd/conf/workers2.properties | the connector read its worker configuration successfully. |
| jk2_init() Found child N in scoreboard slot M | startup bookkeeping: the connector located an Apache worker process in the shared scoreboard. |
| jk2_init() Can't find child N in scoreboard | the same lookup failed - the connector and Apache disagree about which workers exist. |
| mod_jk child init 1 N | a connector child initialising. |
| mod_jk child workerEnv in error state N | a connector child reports its worker environment as broken; requests routed through it to Tomcat cannot be served while this holds. |
| mod_jk2 Shutting down | the connector is stopping, normally as part of a restart. |
| env.createBean2(): Factory error creating X | the connector could not construct a configured object - a configuration or version problem. |
| config.update(): Can't create X | the connector failed to apply a configuration update. |
| uriMap.mapUri() uri must start with / | a malformed URI reached the connector's mapper. |

## Provenance rules

These are what make the number mean anything.

1. **Blind.** The labelling tool never shows the model's verdict. It shows the
   cluster template, up to three real sample events, and, for issues, the link.
2. **Before tuning.** Labels are made, then agreement is computed, then it is
   recorded - before any prompt change. A number produced after tuning against
   these same labels measures nothing.
3. **One prompt version per number.** Every verdict stores the prompt version
   that produced it and the model that answered. The scorecard reports both; a
   mixed-version comparison is thrown away, not averaged.
4. **Skips are recorded, not dropped.** Coverage is part of the result.
5. **A second rater is disclosed as a second rater.** Where an automated rater is
   used for comparison it is reported as such, never as the reference labels.

## Known limitations

- Maintainer labels are themselves inconsistent across projects, partly
  bot-applied, and biased toward issues maintainers engaged with.
- The collapsed taxonomy cannot distinguish crash from error, so the external
  number is measured on four classes, not six.
- Log clusters are annotated by one person, so there is no inter-annotator
  agreement to quote for that half. This is why the external set carries the
  headline and the author-labelled set is reported separately.
- The corpus is two log sources and six repositories. It is not a claim about
  production systems in general.

## Revising the rubric without spending the measurement

The first agreement number (kappa 0.610 over all 109 maintainer-labelled
clusters, prompt 1.1) was recorded before any tuning. That makes it honest and
it also spends it: once a prompt is rewritten in response to the mistakes it
made, the clusters that revealed those mistakes can no longer measure it.

So the labelled set is cut in half once, stratified by class, with a fixed seed
(`eval/split.py`, seed 7, producing `split-dev.csv` and `split-test.csv`):

- **The dev half may be inspected freely.** Disagreements there are read, and
  the rubric is changed in response to them.
- **The test half is scored and not read.** It decides whether a change was
  real. Its individual disagreements are not used to write rules, because that
  would turn it into a second dev set.

Both halves are scored for both prompt versions, and both columns are published.
A change that moves dev and not test has taught the prompt the dev half, which
is worth knowing and not worth shipping.

Prompt 1.2 was written this way. Three boundary rules, each traceable to a
specific dev disagreement:

1. An issue a person filed is never `noise` — a deprecation-warning report had
   been classified as routine chatter.
2. A report that behaviour differs from documentation is the defect it
   describes, even when phrased as a question — "kubelet parameter not working
   as documented" had been classified as `question`.
3. "X does not work" or "X should already do Y" describes a fault in what
   exists, even when worded as a wish — "more freedom to override kernels" had
   been classified as `feature_request`.

Six other dev disagreements were left alone: they are label noise (a migration
task tagged `bug`) or genuine taxonomy mismatch (maintainers tag `enhancement`
on "torch.compile fails to trace X", which this taxonomy reads as a fault).
Writing rules for those would fit the rubric to one project's filing habits.

Prompt 1.1 stays in the code so any published number can be reproduced.
