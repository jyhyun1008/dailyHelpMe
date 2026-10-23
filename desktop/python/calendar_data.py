"""Sunday-first weekly occurrences, matching the original web calendar."""
from datetime import date, timedelta


def event_time(item):
    if item["kind"] == "routine":
        return item["time"]
    at = item.get("at")
    if not at:
        return None
    time = at[11:16]
    return None if (item["kind"], time) in (("schedule", "05:01"), ("todo", "23:59")) else time


def week_data(items, selected):
    selected = date.fromisoformat(selected)
    start = selected - timedelta(days=(selected.weekday() + 1) % 7)
    days = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        key = day.isoformat()
        events = [dict(item, date=key, event_time=event_time(item)) for item in items
                  if item["kind"] == "routine" and offset in item["days"] or item.get("at") and item["at"][:10] == key]
        events.sort(key=lambda item: (item["event_time"] is not None, item["event_time"] or "", item["title"]))
        days.append({"date": key, "events": events})
    return {"start": start.isoformat(), "end": (start + timedelta(days=6)).isoformat(), "days": days}


def today_items(items, selected):
    """Show overdue one-off work without rewriting its original date/time."""
    day = date.fromisoformat(selected)
    weekday = (day.weekday() + 1) % 7
    result = []
    for item in items:
        if item["kind"] == "routine":
            if weekday in item["days"]:
                result.append(dict(item))
            continue
        at = item.get("at")
        if not at:
            continue
        if at[:10] == selected:
            result.append(dict(item))
        elif item["kind"] in ("schedule", "todo") and at[:10] < selected and not item["done"]:
            result.append(dict(item, carryover=True))
    return result
