# Maply: An Enhanced MapQuest Route Analyzer with Webex Notifications

**An Alternative Final Exam Project**
presented to the Department of Information Technology,
College of Information and Computing Sciences, University of Santo Tomas,
in partial fulfilment of the requirements in the course
**IT26210 – System Integration and Architecture**

**Section 4ITG – Group 2**

| Member | Scrum Role | Project Role |
|---|---|---|
| Adriano, Joaquin Miguel A. | Scrum Leader; Developer | Project Lead / Repository Manager |
| Benico, Lance Aidrian F. | Developer | Frontend / UI Designer |
| Cabanada, Kristine Y. | Recorder; Developer | QA Tester / Documentation Lead |
| Chua, Warren V. | Developer | Backend / API Developer |

**Instructor:** Asst. Prof. Mike C. Victorio
**Date:** December 2026

---

## Abstract

Maply extends the MapQuest route script of Laboratory 4.9.2, *Integrate a REST API in a Python Application*, of the Cisco Networking Academy DevNet curriculum into a Flask-based web application for trip planning in Metro Manila. The original script runs only in a command-line terminal, prints unformatted text, processes one trip at a time, and keeps its results on the machine of the person who ran it. Maply addresses these limitations by analyzing routes with the MapQuest Directions API, presenting the results in color-coded tables in either metric or English units, enriching each trip with a weather forecast, and posting a formatted trip summary automatically to a Webex Teams room. The application was developed by a team of four over four one-week Scrum sprints, using GitHub feature branches and reviewed pull requests, automated Python and JavaScript unit tests, and a continuous integration pipeline that runs the test suite on every push and pull request.

## 1. Objectives

### 1.1 Problem Statement

The Laboratory 4.9.2 script demonstrates how a Python program requests route data from a Representational State Transfer (REST) Application Programming Interface (API) and parses the JavaScript Object Notation (JSON) response. However, its output is difficult to read at a glance, and any route information that a group needs must be copied manually into a chat or an email. The team's existing web application already provided an interactive Mapbox GL JS map and GraphHopper routing, but it did not use the MapQuest Directions API covered in the course, did not present route data in tabular form, offered no weather context, and could not share results with other people. Furthermore, users in the Philippines work primarily in metric units, whereas the MapQuest API defaults to miles. The project therefore addresses the need for a single application that analyzes a route, presents the results clearly in the user's preferred unit system, adds weather context for trip planning, and delivers a summary automatically to the people who need it.

### 1.2 General Objective

To develop Maply, a Flask-based web application that analyzes routes from the MapQuest Directions API, presents the results in a colored, table-based interface with user-selectable metric or English units, and automatically sends trip summaries to a Webex Teams room, while applying Agile/Scrum practices, GitHub social coding, Python unit testing, and a continuous integration pipeline.

### 1.3 Specific Objectives

1. To integrate the MapQuest Directions API version 2 route endpoint into the Flask back end over HTTPS, returning the distance, estimated travel time, fuel use where reported, and turn-by-turn maneuvers in metric (kilometers, liters) or English (miles, US gallons) units.
2. To present every route analysis in a colored, table-based web interface alongside the existing Mapbox GL JS map, enriched with a weather forecast for the departure and arrival times.
3. To post a formatted trip summary to a designated Webex Teams room through the Webex Messages API after every successful route analysis, and to allow team members to request a trip summary from a Webex bot.
4. To implement automated unit tests with Python's `unittest` and `unittest.mock` frameworks that cover unit conversion, API response parsing, error handling, and Webex message formatting.
5. To establish a continuous integration pipeline that runs the complete test suite on every commit and pull request, and to route every code change through a feature branch and a reviewed pull request.

## 2. Scope and Limitations

### 2.1 Scope

- **Route analysis:** the MapQuest Directions API (`GET /directions/v2/route`) as the primary route analyzer, with the `unit` parameter set according to the user's choice.
- **Place search and mode comparison:** the GraphHopper Geocoding and Routing APIs, retained from the existing application for place suggestions within Metro Manila and for comparing car, bike, and foot routes, including up to three alternative routes per mode.
- **Commute planning:** jeepney, bus, UV Express, tricycle, and LRT/MRT trips found through the OpenAI API with web search, validated against OpenStreetMap rail station data, with a built-in offline LRT-1, LRT-2, and MRT-3 planner as a fallback.
- **Weather:** the OpenWeatherMap current weather and five-day, three-hour forecast APIs for departure and arrival conditions, with rain and heat advice based on PAGASA heat index bands.
- **Notification:** the Webex Messages API for automatic trip summaries, and a Webex bot that answers @mentions such as "Cubao to Makati" through a signed webhook.
- **User interface:** a responsive web interface with a desktop sidebar and a mobile bottom sheet, color-coded summary and directions tables, a Metric/English toggle, a driving fuel estimate in Philippine pesos (PHP), saved places, and trip history stored in the browser's `localStorage`.
- **Development practices:** Scrum with four one-week sprints (November 13 to December 10, 2026), a shared GitHub repository, feature branches with reviewed pull requests, and a GitHub Actions continuous integration workflow.

### 2.2 Limitations

- **Laboratory environment only.** The application runs on the Flask development server at `http://127.0.0.1:5000` and is not deployed to a public production host. External API calls use HTTPS, but the local application is served over plain HTTP.
- **Lab-grade secrets handling.** API keys and the Webex token are stored in a local `.env` file excluded from version control, not in a dedicated secrets manager. Webex personal access tokens expire after 12 hours; a bot token is therefore recommended.
- **Free-tier API limits.** MapQuest, GraphHopper, OpenWeatherMap, OpenAI, and Mapbox each impose quotas or charges. The application applies per-client rate limits and caching, but heavy use may still exhaust a free plan.
- **No accounts or server database.** Saved places, trip history, and unit preferences are stored only in the current browser and are not synchronized across devices.
- **Estimates only.** Fuel estimates are computed from route distance and user-supplied efficiency and price values; they exclude tolls, traffic, parking, and vehicle load. Commute fares and times are approximate.
- **Geographic scope.** Place search and routing are restricted to Metro Manila.
- **Continuous integration only.** The pipeline automates linting and testing, but automated deployment to a hosted environment is not implemented.
- **Test coverage.** Unit tests mock all external services; no automated end-to-end browser tests were written, and live API behavior was verified manually.

## 3. System Architecture

Maply follows a three-tier architecture made up of a browser client, a Flask application server, and a set of external REST APIs.

- **Client tier:** HTML, Tailwind CSS, and vanilla JavaScript (`templates/`, `static/`), with an interactive map rendered by Mapbox GL JS. The client never calls the routing, weather, or messaging services directly; it sends JSON requests to the Flask endpoints.
- **Application tier:** Flask routes (`routes/api.py`, `routes/webex.py`) delegate to dedicated service modules in `services/` for MapQuest, GraphHopper, weather, commute planning, rail data, unit conversion, and Webex. Every module reads its credentials from the `.env` file through `python-dotenv`, so no secret except the public Mapbox token reaches the browser.
- **External tier:** MapQuest, GraphHopper, OpenWeatherMap, OpenAI, Webex, and Mapbox, all reached over HTTPS.

### 3.1 Application Endpoints

| Endpoint | Method | Purpose | External Service Called |
|---|---|---|---|
| `/api/geocode` | GET | Returns up to five Metro Manila place suggestions. | GraphHopper Geocoding |
| `/api/route` | POST | Calculates a route for the selected car, bike, or foot profile, with fuel estimate. | GraphHopper Routing |
| `/api/compare` | POST | Compares car, bike, and foot routes concurrently and reports unavailable profiles. | GraphHopper Routing |
| `/api/alternatives` | POST | Returns up to three alternative routes labelled by their main road. | GraphHopper Routing |
| `/api/commute` | POST | Plans a public transport trip. | OpenAI (web search); built-in rail planner |
| `/api/mapquest` | POST | Analyzes the route with MapQuest and posts the trip summary to Webex. | MapQuest Directions; OpenWeatherMap; Webex Messages |
| `/api/weather` | GET | Returns departure and arrival weather and a three-hourly forecast. | OpenWeatherMap |
| `/webex/webhook` | POST | Receives signed Webex bot mentions and replies with a trip summary. | Webex Messages; GraphHopper; MapQuest |

### 3.2 Route Analysis and Notification Flow

1. The user selects an origin and a destination and chooses Metric or English units.
2. The client sends the trip to `/api/mapquest`.
3. The server calls the MapQuest route endpoint and validates `info.statuscode`; a non-zero status returns a descriptive error and no Webex message is sent.
4. On success, the server extracts the distance, travel time, fuel use, toll road and highway flags, and maneuvers, and retrieves the weather at departure and arrival.
5. The client renders the color-coded summary and directions tables beside the map.
6. The server posts a Markdown trip summary to the Webex room, truncating very long directions to stay below Webex's 7,439-byte message limit. A failed notification is reported to the user, but it does not prevent the route from being displayed; the panel offers a **Send again** option.

The Webex bot follows a similar flow. Webex sends a signed webhook to `/webex/webhook`; the server verifies the `X-Spark-Signature` HMAC-SHA1 against `WEBEX_WEBHOOK_SECRET`, acknowledges with HTTP `202`, then plans the trip in the background and replies in the question's thread. Messages from bots, including itself, are ignored, and each person may ask five times per minute.

### 3.3 Unit Handling and Fuel Estimation

The MapQuest distance is requested directly in the selected unit, and both unit systems are derived for display so that toggling between them requires no additional API request. Conversions use the exact factors of 1.609344 kilometers per mile and 3.785411784 liters per US gallon. The driving fuel estimate divides the route distance by the user's efficiency (km/L) and multiplies the result by the user's fuel price in PHP. These calculations are kept in `services/converters.py` so that they can be tested in isolation.

## 4. Methodology

### 4.1 Agile Process

The team applied Scrum as described by Schwaber and Sutherland (2020), adapted to the course guidelines with a Scrum Leader and a Recorder. The course instructor acted as the Product Owner. The product backlog was maintained as user stories prioritized with the MoSCoW scheme.

| Sprint | Dates | Sprint Goal |
|---|---|---|
| 1 | Nov 13–19, 2026 | Establish the shared codebase and a working MapQuest route call. |
| 2 | Nov 20–26, 2026 | Deliver the route analyzer interface and automatic Webex notification. |
| 3 | Nov 27–Dec 3, 2026 | Add trip-planning context and automated quality checks. |
| 4 | Dec 4–10, 2026 | Stabilize and release. |

Each sprint began with sprint planning, included short daily check-ins, and ended with a sprint review and a retrospective. A backlog item was considered done only when its code had been merged through a reviewed pull request, its tests passed in continuous integration, the change had been checked manually in the browser, and this README had been updated where needed.

### 4.2 Version Control

All development took place in a shared GitHub repository. Each backlog item was developed on its own feature branch (for example, `feature/blue-theme`) and merged into `main` through a pull request reviewed by a member other than the author. Feature branches are retained after merging as a record of the work. The `.gitignore` file excludes `.env`, virtual environments, and Python cache files.

### 4.3 Testing and Continuous Integration

The Python back end is tested with `unittest`, and every external service is replaced with `unittest.mock`, so the tests run without network access and consume no API quota. The suite covers unit conversion, MapQuest response parsing and status-code handling, Webex message formatting and delivery, the Webex bot and webhook signature verification, the rail planner, and the Flask endpoints through Flask's test client. At the time of writing, all 166 Python test cases pass. The browser modules for saved places, trip history, and weather are tested with the Node.js test runner.

The continuous integration pipeline is defined in `.github/workflows/ci.yml` and runs on every push and pull request to `main`. It lints the Python code for syntax errors and undefined names, runs the Python test suite on Python 3.10 through 3.14, checks the syntax of every JavaScript file, and runs the JavaScript tests. A failing job marks the pull request as failed.

## 5. Installation and Usage

### 5.1 Prerequisites

- Git and Python 3.10 or newer (on Windows, include the `py` launcher). Node.js 20 or newer is needed only to run the JavaScript tests.
- Internet access, since the application calls external APIs and loads map tiles and frontend libraries from public CDNs.
- The following credentials:
  - a GraphHopper API key with Geocoding and Routing access (required);
  - a Mapbox **public** access token beginning with `pk.`, restricted to localhost;
  - a MapQuest API key for the route analyzer;
  - a Webex bot access token and room ID for trip summaries, and a random webhook secret for the bot;
  - an OpenWeatherMap API key (the free plan is sufficient; new keys may take up to two hours to activate);
  - optionally, an OpenAI API key for Commute mode. Without it, Commute mode uses the built-in LRT/MRT planner.

### 5.2 Setup

Clone the repository and enter the project directory:

```powershell
git clone https://github.com/joaquinadriano/Maply.git
cd Maply
```

Create and activate a virtual environment (Windows PowerShell):

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On macOS or Linux, use `python3 -m venv .venv` followed by `source .venv/bin/activate`.

Install the dependencies:

```powershell
python -m pip install -r requirements.txt
```

Copy the example environment file and replace the placeholder values with your credentials:

```powershell
Copy-Item .env.example .env
```

```dotenv
GRAPHHOPPER_API_KEY=your_graphhopper_key
MAPBOX_ACCESS_TOKEN=pk.your_public_mapbox_token
MAPQUEST_API_KEY=your_mapquest_key
WEBEX_ACCESS_TOKEN=your_webex_bot_token
WEBEX_ROOM_ID=your_webex_room_id
WEBEX_WEBHOOK_SECRET=your_random_secret
OPENWEATHER_API_KEY=your_openweathermap_key
OPENAI_API_KEY=your_openai_key
```

The `.env` file is ignored by Git. Never place real credentials in `.env.example`.

### 5.3 Running the Application

```powershell
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in a browser. The server listens on port 5000 unless `PORT` is changed in `.env`. Restart the server after editing `.env`, and press **Ctrl+C** to stop it.

### 5.4 Webex Bot Setup

1. Create a bot at [developer.webex.com/my-apps/new/bot](https://developer.webex.com/my-apps/new/bot), place its token in `WEBEX_ACCESS_TOKEN`, and add the bot to the Webex space.
2. Generate a webhook secret, for example with `python -c "import secrets; print(secrets.token_hex(24))"`, and place it in `WEBEX_WEBHOOK_SECRET`. Without this secret, the webhook endpoint refuses every request with HTTP `503`.
3. Expose the local server over HTTPS with a tunnel such as [ngrok](https://ngrok.com/) (`ngrok http 5000`).
4. Register the webhook with the tunnel's URL, repeating this step whenever the URL changes:

```powershell
python scripts/webex_webhook.py register https://your-tunnel.ngrok-free.app
```

The `list` and `delete` subcommands show and remove the webhook. In Webex, the bot is then used as follows:

```
@Maply Cubao to Makati
@Maply Quiapo to BGC, bike
@Maply UP Diliman to SM Megamall, walk in miles
@Maply help
```

### 5.5 Running the Tests

```powershell
python -m unittest discover -s tests -v
```

```powershell
node --test "tests/js/*.test.mjs"
```

### 5.6 Troubleshooting

- **`python` or `py` is not recognized:** install Python and ensure it is on the `PATH`.
- **`ModuleNotFoundError` on startup:** activate `.venv` and reinstall the requirements.
- **The map shows setup instructions:** confirm that `MAPBOX_ACCESS_TOKEN` is a valid public token whose allowed URLs include the local address, then restart the server.
- **Place search or routing fails:** confirm that the GraphHopper key is set and that the account supports the selected profile.
- **The MapQuest panel reports that Webex is not set up or the token expired:** set `WEBEX_ACCESS_TOKEN` and `WEBEX_ROOM_ID`, preferably with a bot token, which does not expire.
- **Port 5000 is already in use:** set a different `PORT` in `.env` and open that port instead.

## 6. Conclusion and Recommendations

Maply met its objectives by replacing the command-line output of Laboratory 4.9.2 with a web-based route analyzer that presents MapQuest results in color-coded tables in the user's preferred unit system, adds weather context, and shares each trip automatically with the team through Webex. The project also showed that the reliability of an integration depends as much on handling the documented failure cases of an API, such as invalid status codes, timeouts, rate limits, and expired tokens, as on processing its successful responses, and that short sprints, reviewed pull requests, and automated tests reinforce one another.

For future development, the team recommends server-side accounts and a database so that saved places and trip history are available across devices; moving secrets to a managed secrets service; containerizing the application and serving it with a production WSGI server behind an HTTPS reverse proxy; extending the pipeline from continuous integration to continuous delivery with automated deployment to a staging environment; caching more API responses to reduce quota usage; and adding automated browser tests for the JavaScript front end.

## References

- Cisco Networking Academy. (n.d.). *DevNet Associate* [Course materials; Lab 4.9.2: Integrate a REST API in a Python application]. Cisco Systems. https://www.netacad.com/
- Driessen, V. (2010, January 5). *A successful Git branching model*. https://nvie.com/posts/a-successful-git-branching-model/
- Fielding, R. T. (2000). *Architectural styles and the design of network-based software architectures* [Doctoral dissertation, University of California, Irvine].
- Fowler, M. (2006). *Continuous integration*. https://martinfowler.com/articles/continuousIntegration.html
- GraphHopper GmbH. (n.d.). *Plans and rate limits*. https://docs.graphhopper.com/
- Hanson, T. (2025, April 14). *Rate limiting and the Webex API*. Webex for Developers Blog. https://developer.webex.com/blog/rate-limiting-and-the-webex-api
- Mapbox. (n.d.). *Mapbox GL JS*. https://docs.mapbox.com/mapbox-gl-js/
- MapQuest. (n.d.). *Directions API*. https://developer.mapquest.com/documentation/api/directions/
- Pallets. (n.d.). *Flask documentation*. https://flask.palletsprojects.com/
- Python Software Foundation. (n.d.). *unittest: Unit testing framework*. https://docs.python.org/3/library/unittest.html
- Schwaber, K., & Sutherland, J. (2020). *The Scrum guide*. https://scrumguides.org/scrum-guide.html
- Webex by Cisco. (n.d.). *Webex REST API basics*. https://developer.webex.com/messaging/docs/basics
