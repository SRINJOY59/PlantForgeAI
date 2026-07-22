# 4. The MCP server: the plant graph outside the app

## What MCP is

The Model Context Protocol is an open standard for how an AI assistant discovers
and calls capabilities that live outside itself. A **client**, embedded in
whatever assistant the user is talking to, connects to a **server** that exposes
a set of tools.

The exchange is small: the client asks what the server can do, and gets back a
list of tools, each with a name, a natural-language description and a schema for
its arguments. The model may then call any of them by name. It never learns how a
tool works internally — only what it is for, what it needs, and what it returns.

That indirection is the value. Before it, connecting an assistant to a system
meant a bespoke integration written for one assistant and rewritten for the next.
Now a capability is described once and becomes available to every MCP-capable
client, with the assistant choosing when to use it from the description alone.

## Why PlantForge needs one

Everything in the previous sections is reachable through one web application,
which assumes the engineer comes to us. In practice they do not — they are in a
modification proposal, a shutdown review spreadsheet, or whatever assistant their
organisation has standardised on. Asking them to stop, open a tab, re-type an
equipment tag and copy an answer back is exactly the friction that leaves plant
knowledge unused in the first place.

The MCP server removes it: failure history, governing standards, process
connections and grounded question-answering become tools an assistant can call
*inside the work already in progress*.

What makes this worth doing properly, rather than handing out a database
connection, is that **the discipline travels with the data.** Every result
carries the same citations to real documents, the same confidence signal, and the
same engineer corrections that overrule the records they were filed against. An
assistant given raw query access would produce confident unsourced claims about
pressure vessels. An assistant given these tools cannot, because every path to
the data returns the evidence with it.

## Implementation

```
   ┌──────────────────────────────┐
   │  Any MCP-capable AI client   │  asks what tools exist,
   └───────────────┬──────────────┘  then calls them by name
                   │  JSON-RPC over stdio
   ┌───────────────▼──────────────────────────────────────────┐
   │  PlantForge MCP server                                   │
   │                                                          │
   │   ask_plant · assess_change · plant_status               │
   │                        │                                 │
   │                        ▼                                 │
   │        via the GATEWAY — inherits auth, rate             │
   │        limits, full retrieval + grounding                │
   │                                                          │
   │   get_failure_history     get_fix_procedures             │
   │   get_connected_equipment get_work_orders                │
   │   get_governing_clauses   get_documents_mentioning       │
   │                        │                                 │
   │                        ▼                                 │
   │        DIRECT read-only graph access,                    │
   │        connection opened lazily                          │
   └──────────────────────────────────────────────────────────┘
```

**Nine tools across two access paths, and the split is deliberate.** Anything
that costs money or must be governed — open questions, change assessment, system
status — goes through the gateway, inheriting authentication, per-user rate
limiting and the full grounding pipeline. The six structured lookups are cheap
read-only traversals and go straight to the graph. Routing everything through the
gateway would tax trivial lookups; routing everything direct would bypass the
controls that make the expensive paths safe.

**The tool descriptions are the interface.** The model chooses between tools on
name, schema and description alone, so those descriptions carry engineering
intent: the failure-history tool states that a correction overrules the documents
it was filed against, and change assessment is described as something to call
*before* recommending any modification. A server-level instruction tells the
model to never invent plant data the server did not return.

**It is a thin adapter, not a second system.** No retrieval logic, no reasoning
and no data of its own — every tool resolves to a capability that already
existed. An answer obtained through an assistant and the same answer obtained
through the web application come from one pipeline, carry the same citations, and
are stamped with the same graph version. There is no second implementation to
drift.
