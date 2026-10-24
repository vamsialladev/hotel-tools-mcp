# Contributing

1. Branch from `main`, open a pull request; CI must pass. Commits follow
   [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
2. **A new tool:** add the function to `src/hotel_tools/tools.py` (take the tenant from `ctx.principal`, never from
   arguments), a wrapper with typed parameters in `server.py`, a row in `rbac.TOOLS_BY_ROLE`, tests for every role
   (allowed and denied) and eval cases.
3. **A new role:** add it to `auth.ROLES`, `rbac.TOOLS_BY_ROLE` and `rbac.BOOKING_FIELDS`, plus tests.
4. **Stage 1 changed:** `python scripts/sync_policy.py --ref <tag>`, then re-run the eval.
5. Run `make check` before pushing.
