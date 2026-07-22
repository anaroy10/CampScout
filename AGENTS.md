# CampScout repository rules

These rules apply to the entire repository and to every future task unless a more restrictive instruction is provided.

1. The project is CampScout, a Python, MySQL, and Streamlit application.
2. Raw CSV files are immutable and must never be edited.
3. Do not invent missing values.
4. Missing amenity information remains `UNKNOWN`, not `NO`.
5. Activities belong to Recreation Areas, not directly to Campgrounds.
6. National Parks are related to Campgrounds through calculated geographic distance, not a direct foreign key.
7. Do not use `site_id` as the campground primary key unless profiling proves it is globally unique.
8. Do not automatically merge fuzzy duplicate candidates.
9. Use only relative repository paths.
10. Use parameterized SQL queries.
11. Never hard-code credentials.
12. Never commit or push automatically.
13. Never run destructive Git commands.
14. Run relevant tests before declaring a task complete.
15. Preserve raw identifiers without accidental float conversion or `.0` suffixes.
16. Update documentation whenever business rules or schemas change.
17. The target environment is Windows, VS Code, Python, MySQL, and Streamlit.

## Scope guardrails

The supported product flow is park selection, radius selection, discovery of nearby Forest Service campgrounds, filtering by Recreation Area activities and supported campground attributes, and display of straight-line distance plus official campground information.

Do not add user ratings, reviews, electrical hookups, sewer hookups, vehicle-length recommendations, booking functionality, or machine-learning recommendations.

The files under `legacy/` are reference material only. They do not override the raw data, current specifications, profiling results, or these rules.
