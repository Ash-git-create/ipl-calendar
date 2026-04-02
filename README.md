# IPL 2026 Calendar

Subscribe to the IPL 2026 schedule directly in your calendar. The feeds are updated automatically from GitHub Actions to keep up with fixture changes and reschedules.

## Quick Add Pages

- [Full IPL Calendar](https://ash-git-create.github.io/ipl-calendar/?calendar=full)
- [Chennai Super Kings](https://ash-git-create.github.io/ipl-calendar/?calendar=csk)
- [Delhi Capitals](https://ash-git-create.github.io/ipl-calendar/?calendar=dc)
- [Gujarat Titans](https://ash-git-create.github.io/ipl-calendar/?calendar=gt)
- [Kolkata Knight Riders](https://ash-git-create.github.io/ipl-calendar/?calendar=kkr)
- [Lucknow Super Giants](https://ash-git-create.github.io/ipl-calendar/?calendar=lsg)
- [Mumbai Indians](https://ash-git-create.github.io/ipl-calendar/?calendar=mi)
- [Punjab Kings](https://ash-git-create.github.io/ipl-calendar/?calendar=pbks)
- [Rajasthan Royals](https://ash-git-create.github.io/ipl-calendar/?calendar=rr)
- [Royal Challengers Bengaluru](https://ash-git-create.github.io/ipl-calendar/?calendar=rcb)
- [Sunrisers Hyderabad](https://ash-git-create.github.io/ipl-calendar/?calendar=srh)

Use a quick-add page if you want the browser to offer the best next step for Apple Calendar, Outlook, or Google Calendar.

## Add To Google Calendar

1. Open [Google Calendar](https://calendar.google.com).
2. Open `Settings`.
3. Choose `Add calendar` > `From URL`.
4. Paste the calendar link you want from the list above.
5. Click `Add calendar`.

## Add To Apple Calendar On iPhone Or iPad

1. Open `Settings`.
2. Go to `Calendar` > `Accounts` > `Add Account`.
3. Choose `Other` > `Add Subscribed Calendar`.
4. Paste the calendar link you want from the list above.
5. Tap `Next`, then `Save`.

## Add To Apple Calendar On Mac

1. Open the `Calendar` app.
2. Go to `File` > `New Calendar Subscription`.
3. Paste the calendar link you want from the list above.
4. Click `Subscribe`.
5. Set auto-refresh to `Every Day`.

## Add To Outlook

1. Open Outlook and switch to `Calendar`.
2. Choose `Add calendar`.
3. Select `Subscribe from web`.
4. Paste the calendar link you want from the list above.
5. Confirm the import.

## Notes

- Calendar apps automatically convert match times to the viewer's local timezone.
- GitHub Actions runs daily and can also be triggered manually.
- Primary source: [CricAPI](https://cricapi.com).
- Fallback source: Cricbuzz schedule data embedded in the series page HTML.
- If CricAPI is rate-limited, the workflow can still complete through the Cricbuzz fallback.
