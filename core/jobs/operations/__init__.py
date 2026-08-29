"""Registered job operations (MKT-11C).

Only :mod:`demo` ships in this milestone — dev/test-only operations that
exercise the job lifecycle. Real operations (SEO report, analytics import,
eventually ``run-campaign``) register here in later milestones by adding a
sibling module and an ``OperationSpec``, never by editing the runner.
"""

from __future__ import annotations
