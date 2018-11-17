import requests
import re
import logging
import pytz
from bs4 import BeautifulSoup
from django.conf import settings
from collections import deque
from dateutil.parser import parse
from datetime import datetime, timedelta
from .models import (Terminal, Route, Ferry, Sailing, Destination, Status,
                     SailingEvent, ArrivalTimeEvent, ArrivedEvent, StatusEvent,
                     FerryEvent, DepartureTimeEvent, DepartedEvent,
                     PercentFullEvent, CarWaitEvent, OversizeWaitEvent)

logger = logging.getLogger(__name__)

timezone = pytz.timezone("America/Vancouver")

def get_actual_departures():
    url = "{}/{}".format(settings.BCF_BASE_URL, "actualDepartures.asp")

    try:
        logger.info("Querying BCF for data...")
        response = requests.get(url)
        if response.status_code == 200:
            logger.info("Successfully queried BCF for data")
            data = response.text
        else:
            logger.error("Could not retrieve details from the BC Ferries website: {}".format(response.status_code))
            return False
    except:
            logger.error("Could not retrieve details from the BC Ferries website.")
            return False

    b = BeautifulSoup(data, 'html.parser')

    routes = deque(
        b.find('td', class_='content').find('table').find_all('table')
    )

    date = b.find('span', class_='titleSmInv').text
    print("Status for {}".format(date))

    routes_list = []
    terminals = {}

    while len(routes) != 0:
        route = routes.popleft()
        route_name, sailing_time = route.span.decode_contents().split('<br/>')
        source, destination = re.search(r'(.*) to (.*)', route_name).groups()
        source_code, route_code = re.search(r'#([A-Z]+)(\d+)', route.find_previous_sibling().attrs['name']).groups()
        print("Found route: {}".format(route_name))
        print("-> source: {} destination: {}".format(source, destination))
        print("-> {} (route {})".format(source_code, route_code))

        terminals[source] = source_code

        sailings = routes.popleft()

        route_details = {
            "source_code": source_code,
            "source": source,
            "destination": destination,
            "route_name": route_name,
            "sailing_time": sailing_time,
            "route_code": route_code
        }

        sailings_list = []

        for sailing in sailings.find_all('tr')[1:]:
            ferry, scheduled, actual, eta_arrival, status = [td.text.strip() for td in sailing.find_all('td')]
            print("  -> {} (Scheduled: {}, Actual: {}, ETA: {}, Status: {}".format(
                ferry, scheduled, actual, eta_arrival, status
            ))

            sailings_list.append({
                "ferry": ferry,
                "scheduled": scheduled,
                "actual": actual,
                "eta_or_arrival": eta_arrival,
                "status": status
            })

        route_details.update({"sailings": sailings_list})
        routes_list.append(route_details)

    for route in routes_list:

        logger.debug("--- Parsing new route ---")

        destination_name = route['destination']
        source_name = route['source']
        source_code = route['source_code']

        # Source terminal
        source_o, created = Terminal.objects.get_or_create(
            name=source_name,
            short_name=source_code
        )

        if created:
            logger.info("Created terminal {} for {}".format(
                source_code, source_name
            ))
        else:
            logger.info("Found terminal {} for {}".format(
                source_o.name, source_o.short_name
            ))

        destination_name = route['destination']

        # See if the destination is a terminal, or just a description
        if destination_name not in terminals:
            logger.info("{} not found in terminal list".format(destination_name))

            # Create Destination object without an associated terminal
            dest_o, created = Destination.objects.get_or_create(
                name=destination_name
            )

            if created:
                logger.info("Created destination for {}".format(
                    destination_name
                ))
            else:
                logger.info("Found destination for {}".format(
                    dest_o.name
                ))
        else:
            destination_o, created = Terminal.objects.get_or_create(
                name=destination_name,
                short_name=terminals[destination_name]
            )

            if created:
                logger.info("Created terminal {} for {}".format(
                    destination_name, terminals[destination_name]
                ))
            else:
                logger.info("Found terminal {} for {}".format(
                    destination_o.name, destination_o.short_name
                ))

            # Create Destination object (different to the actual Terminal
            # object for the destination
            dest_o, created = Destination.objects.get_or_create(
                name=destination_name,
                terminal=destination_o
            )

            if created:
                logger.info("Created destination for {} ({})".format(
                    destination_name, destination_o
                ))
            else:
                logger.info("Found destination for {} ({})".format(
                    dest_o.name, dest_o.terminal
                ))

        # Create Route
        route_code = route['route_code']

        route_o, created = Route.objects.get_or_create(
            name=route['route_name'],
            source=source_o,
            destination=dest_o,
            route_code=route_code
        )

        if created:
            logger.info("Created route {} ({} -> {})".format(
                route_o.route_code, route_o.source, route_o.destination
            ))
        else:
            logger.info("Found route {} ({} -> {})".format(
                route_o.route_code, route_o.source, route_o.destination
            ))

        for sailing in route['sailings']:
            logger.debug(">>>>>> Parsing new sailing")
            ferry = sailing['ferry']
            scheduled_departure = sailing['scheduled']
            actual_departure = sailing['actual']
            eta_or_arrival = sailing['eta_or_arrival']
            status = sailing['status']

            ferry_o, created = Ferry.objects.get_or_create(
                name=ferry
            )

            if created:
                logger.info("Created ferry {}".format(ferry))
            else:
                logger.info("Found ferry {}".format(ferry))

            sched = parse("{} {}".format(date, scheduled_departure))
            sched = timezone.localize(sched)

            if actual_departure:
                actual = parse("{} {}".format(date, actual_departure))
                actual = timezone.localize(actual)
                departed = True
            else:
                logger.info("No actual departure time for this sailing")
                actual = None
                departed = False

            if eta_or_arrival:
                if 'ETA' in eta_or_arrival:
                    # we have an ETA
                    eta = re.search(r'ETA: (.*)', eta_or_arrival).groups()[0]
                    eta_or_arrival = parse("{} {}".format(date, eta))
                    eta_or_arrival = timezone.localize(eta_or_arrival)
                    logger.info("ETA for this sailing is {}".format(eta_or_arrival))
                    arrived = False
                else:
                    eta_or_arrival = parse("{} {}".format(date, eta_or_arrival))
                    eta_or_arrival = timezone.localize(eta_or_arrival)
                    logger.info("Arrival time for this sailing was {}".format(eta_or_arrival))
                    arrived = True
            else:
                logger.info("No ETA or arrival time")
                eta_or_arrival = None
                arrived = False

            # Status
            status_o, created = Status.objects.get_or_create(
                status=status
            )

            if created:
                logger.info("Created status {}".format(status))
            else:
                logger.info("Found status {}".format(status))

            sailing_o, created = Sailing.objects.get_or_create(
                route=route_o,
                scheduled_departure=sched
            )

            if created:
                logger.info("Created sailing {}".format(sailing_o))
            else:
                logger.info("Found sailing {}".format(sailing_o))

            # Check differences
            if sailing_o.ferry != ferry_o:
                logger.info("Ferry has changed ({} to {})".format(
                    sailing_o.ferry, ferry_o
                ))
                event_o = FerryEvent(
                    sailing=sailing_o,
                    old_ferry=sailing_o.ferry,
                    new_ferry=ferry_o
                )
                sailing_o.ferry = ferry_o

                event_o.save()
                sailing_o.save()

            if sailing_o.actual_departure != actual:
                logger.info("Actual departure has changed ({} to {})".format(
                    sailing_o.actual_departure, actual
                ))

                if sailing_o.actual_departure is None:
                    logger.info("Sailing has departed")

                    departed_o = DepartedEvent(
                        sailing=sailing_o
                    )
                    departed_o.save()

                event_o = DepartureTimeEvent(
                    sailing=sailing_o,
                    old_departure=sailing_o.actual_departure,
                    new_departure=actual
                )
                sailing_o.actual_departure = actual

                event_o.save()
                sailing_o.save()

            if sailing_o.departed != departed:
                logger.info("Departed has changed ({} to {})".format(
                    sailing_o.departed, departed
                ))
                event_o = DepartedEvent(
                    sailing=sailing_o
                )
                sailing_o.departed = departed

                event_o.save()
                sailing_o.save()

            if sailing_o.eta_or_arrival_time != eta_or_arrival:
                logger.info("ETA or arrival time has changed ({} to {})".format(
                    sailing_o.eta_or_arrival_time, eta_or_arrival
                ))
                event_o = ArrivalTimeEvent(
                    sailing=sailing_o,
                    old_arrival=sailing_o.eta_or_arrival_time,
                    new_arrival=eta_or_arrival,
                    is_eta=not arrived
                )
                sailing_o.eta_or_arrival_time = eta_or_arrival

                event_o.save()
                sailing_o.save()

            if sailing_o.arrived != arrived:
                logger.info("Arrival has changed ({} to {})".format(
                    sailing_o.arrived, arrived
                ))
                event_o = ArrivedEvent(
                    sailing=sailing_o
                )
                sailing_o.arrived = arrived

                event_o.save()
                sailing_o.save()

            if sailing_o.status != status_o:
                logger.info("Status has changed ({} to {})".format(
                    sailing_o.status, status_o
                ))
                event_o = StatusEvent(
                    sailing=sailing_o,
                    old_status=sailing_o.status,
                    new_status=status_o
                )
                sailing_o.status = status_o

                event_o.save()
                sailing_o.save()


def get_current_conditions():
    url = "{}/{}".format(settings.BCF_BASE_URL, "at-a-glance.asp")

    try:
        logger.info("Querying BCF for data...")
        response = requests.get(url)
        if response.status_code == 200:
            logger.info("Successfully queried BCF for data")
            data = response.text
        else:
            logger.error("Could not retrieve details from the BC Ferries website: {}".format(response.status_code))
            return False
    except:
            logger.error("Could not retrieve details from the BC Ferries website.")
            return False

    s = BeautifulSoup(data, 'html.parser')

    terminals = {}

    j_routes = []
    # Get sections
    for section in s.find_all('tbody'):
        current_terminal = None
        if section.span:
            terminal_name = section.span.contents[0]
            terminal_id = terminal_name.lower().replace(' ', '_')
        else:

            # parse out each sailing
            for route in section.find_all('tr', recursive=False)[1:-1]:
                j_route = {}
                route_name = route.td.text
                details = route.find_all('td', recursive=False)
                route_id = re.match('.*route=(\d+)&dept=(\w+).*', details[7].a.get('href')).groups()[0]
                j_route['route_id'] = route_id
                j_route['route_name'] = route_name

                if details[1].div.text == "N/A":
                    next_sailing = "N/A"
                    percent_full = "N/A"
                    j_route['sailings'] = None
                else:
                    sailing_details = {}
                    sailings = details[1].div.table.find_all('tr')
                    j_sailings = []
                    for sailing in sailings:
                        next_sailing = sailing.td.text
                        percent_full = int(sailing.td.next_sibling.text.split('% ')[0])

                        sailing_details.update({next_sailing: percent_full})

                        j_sailings.append({
                            'time': next_sailing,
                            'percent_full': percent_full
                        })

                    j_route['sailings'] = j_sailings

                    car_waits = int(details[2].text.rstrip('\n'))
                    oversize_waits = int(details[3].text.rstrip('\n'))

                    j_route['car_waits'] = car_waits
                    j_route['oversize_waits'] = oversize_waits

                next_sailings = details[4].text.lstrip(' ').split(' ')
                j_route['later_sailings'] = next_sailings

                j_routes.append(j_route)

    for route in j_routes:
        route_name = route['route_name']
        logger.debug("Found route {}".format(route_name))

        route_o = Route.objects.get(name=route_name)

        car_waits = route.get('car_waits', None)
        oversize_waits = route.get('oversize_waits', None)

        if route_o.car_waits != car_waits:
            logger.debug("Car waits has changed ({} -> {})".format(
                route_o.car_waits, car_waits
            ))

            carwaitevent_o = CarWaitEvent(
                route=route_o,
                old_value=route_o.car_waits,
                new_value=car_waits
            )

            route_o.car_waits = car_waits

            carwaitevent_o.save()
            route_o.save()

        if route_o.oversize_waits != oversize_waits:
            logger.debug("Oversize waits has changed ({} -> {})".format(
                route_o.oversize_waits, oversize_waits
            ))

            oversizewaitevent_o = OversizeWaitEvent(
                route=route_o,
                old_value=route_o.oversize_waits,
                new_value=oversize_waits
            )

            route_o.oversize_waits = oversize_waits

            oversizewaitevent_o.save()
            route_o.save()


        if not route['sailings']:
            logger.debug("No more sailings today for this route")
        else:
            for sailing in route['sailings']:
                logger.debug("Found sailing at {}".format(sailing['time']))

                # Build time
                today = datetime.now(timezone).strftime("%Y-%m-%d")
                sailing_time = parse("{} {}".format(
                    today,
                    sailing['time']
                ))
                sailing_time = timezone.localize(sailing_time)
                logger.debug("Sailing time is {}".format(sailing_time))

                # Find sailing
                sailing_o = Sailing.objects.get(
                    route=route_o,
                    scheduled_departure=sailing_time
                )

                percent_full = sailing['percent_full']

                if sailing_o.percent_full != percent_full:
                    logger.debug("Percent full has changed ({} -> {})".format(
                        sailing_o.percent_full, percent_full
                    ))

                    percentfull_o = PercentFullEvent(
                        sailing=sailing_o,
                        old_value=sailing_o.percent_full,
                        new_value=percent_full
                    )

                    sailing_o.percent_full = percent_full

                    percentfull_o.save()
                    sailing_o.save()

        for sailing in route['later_sailings']:
            logger.debug("Found later sailing {}".format(sailing))

            if sailing.startswith('*'):
                # Sailing is tomorrow
                tomorrow = (datetime.now(timezone) + timedelta(days=1)).strftime("%Y-%m-%d")
                sailing_time = parse("{} {}".format(
                    tomorrow, sailing[1:]
                ))
                sailing_time = timezone.localize(sailing_time)
                logger.debug("Later sailing is tomorrow: {}".format(
                    sailing_time
                ))

            else:
                today = datetime.now(timezone).strftime("%Y-%m-%d")
                sailing_time = parse("{} {}".format(
                    today, sailing
                ))
                sailing_time = timezone.localize(sailing_time)
                logger.debug("Later sailing is today: {}".format(
                    sailing_time
                ))

            sailing_o, created = Sailing.objects.get_or_create(
                route=route_o,
                scheduled_departure=sailing_time
            )

            if created:
                logger.debug("Created sailing for {}".format(sailing_time))
            else:
                logger.debug("Sailing for {} already existed".format(sailing_time))
