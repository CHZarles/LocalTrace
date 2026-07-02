# LocalTrace Web Settings

Manual smoke steps:

1. Start LocalTrace core on `127.0.0.1:8765`.
2. Open `http://127.0.0.1:8765/`.
3. Confirm health shows service, bind, database, recent event count, tracking,
   Windows probe, and browser extension rows.
4. Change a safe setting and save.
5. Confirm `GET /settings` reflects the saved value.
6. Add an app or domain `mask` or `drop` privacy rule.
7. Confirm the rule appears in the Privacy table.
8. Delete the rule and confirm it is removed.
9. Pause tracking and confirm `POST /events` does not store a new event.
10. Resume tracking and confirm `POST /events` stores a new event.
