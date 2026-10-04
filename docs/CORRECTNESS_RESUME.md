# Resuming correctness work

[HANDOFF.md](HANDOFF.md) is the single source for current status, ownership,
resume order, overlay range, build versions and last-observed resource state.
This guide does not copy those changing values.

1. Fetch and fast-forward the repository, then read HANDOFF's claims and resource
   holders. Preserve dirty shared ATFE/LK and evidence; never reset, stash or
   reapply overlays to synchronize an existing live tree.
2. Claim an unowned item and successfully push the required reservations before
   implementation. Both agents use the same pool.
3. Verify current tool/input identities and access. The live-tree lock covers
   shared sources/builds; Pi/COM5 needs a separate reservation. Local memories
   and historical snapshots do not grant ownership or prove availability.
4. Follow the item's acceptance criteria, export one overlay per source item,
   replay the full series and refresh coverage after backend/image changes.
   Keep execution claims within reviewed contracts and observed scope.
5. Before stopping, update HANDOFF, log results/evidence/resource state, publish
   releases and sync repository copies and project memory.

- [Acceptance-criteria index](CORRECTNESS_PRIORITY_TODO.md)
- [Latest reconciled review](CORRECTNESS_REVIEW_ASTRA_0057.md)
- [Local build/setup](WSL_BUILD.md)
- [Repository health command and cleanup](REPO_HEALTH.md)
- [Historical checkpoints](CORRECTNESS_CHECKPOINT_HISTORY.md)
- [Historical handoff log](HANDOFF_HISTORY.md)
