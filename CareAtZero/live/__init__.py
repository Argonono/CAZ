"""
Live data for CareAtZero.

Every search uses current records from official public sources instead of a
fixed list:

    hrsa.py           HRSA health centers (federal)          -> Medical, sliding scale
    samhsa.py         SAMHSA FindTreatment.gov (federal)      -> Mental health / substance use
    nc_safety_net.py  NC DHHS Safety Net list (state)         -> Free clinics, dental, health departments
    ram_events.py     Remote Area Medical calendar feed       -> Free pop-up clinics (dental, vision, medical)
    zip_centroids.py  U.S. Census ZIP code locations         -> places any U.S. ZIP on the map

sources.py fetches them all (in parallel, cached for a few hours) and reports
which ones worked. Rules every connector follows:
  - never invent data: if a source can't be reached, it is reported as
    unavailable instead of filled in
  - only label something "Free" when the source itself says it is free
  - stamp each record with when it was fetched ("last checked")
"""
