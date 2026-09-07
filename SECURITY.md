# Reporting a security problem

Write to [andrew@gamakon.ai](mailto:andrew@gamakon.ai) with the wheel version
(`python -c "import ultradim; print(ultradim.__version__)"`), your platform,
and what you observed. Do not open a public issue for a security problem.

You will get an acknowledgement within five working days.

The database runs inside your own process and opens no network port. The
client-server version, available on request, does open one; report anything
about it the same way.
