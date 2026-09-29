# Pantry Cook

A single-user web app for tracking a home pantry and turning a plain sentence into a structured, quantity-aware meal proposal. Built with FastAPI, LangGraph, Next.js, and shadcn/ui.

The home page is the pantry: items grouped by urgency, with quick-add, inline edit, and delete. A sentence such as `2 leeks and 500 g chicken` previews those quantities, then adds them. A sentence that does not parse, or that mixes units of different kinds, changes nothing.
