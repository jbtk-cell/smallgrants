# Contributing

## Reporting a problem

Open an issue. The most useful reports name a specific foundation EIN and what
the site said about it, because almost every defect found so far was a wrong
claim about a real foundation rather than a crash.

If the corpus says something false about a foundation, that is the highest
priority category of bug here. Include the EIN and what the filing actually says.

## Contributing changes

Fork, branch, open a pull request. Two expectations:

- **Run the tests.** `pytest tests/` should stay green. There are 62.
- **A behaviour fix comes with a test that fails without it.** Every test in
  `tests/test_critic.py` corresponds to a specific wrong answer this software
  gave a user, and that is deliberate. A fix without a test tends to come back.

Rebuilding the corpus is not required to contribute. Most changes can be checked
against the tests alone, and the pipeline commands are in the README if you do
need a corpus.

## A note on claims

This project makes assertions to people deciding where to spend limited time
applying for money. Wherever the record is too thin to support a claim, the
correct behaviour is to say so and show the gap, not to guess and sound
confident. Changes that make the software more certain than the underlying
filings justify will be declined, however well they perform.

## Support

Open an issue with the `question` label.
