import json
import datetime
from datetime import timedelta
import requests
from flask import current_app, request
from slugify import slugify

region_field = "region"

def parser():
    output = {}
    data = {}
    result_json = None

    spreadsheet_id = current_app.config["SPREADSHEET_ID"]
    worksheet_names = current_app.config["WORKSHEET_NAMES"]
    cache_timeout = int(current_app.config["API_CACHE_TIMEOUT"])
    store_in_s3 = current_app.config["STORE_IN_S3"]
    bypass_cache = request.args.get("bypass_cache", "false")
    if store_in_s3 == "true":
        bypass_cache = request.args.get("bypass_cache", "true")
    if spreadsheet_id is not None:
        api_key = current_app.config["API_KEY"]
        authorize_url = current_app.config["AUTHORIZE_API_URL"]
        url = current_app.config["PARSER_API_URL"]
        if authorize_url != "" and api_key != "" and url != "":
            token_params = {
                "api_key": api_key
            }
            token_headers = {'Content-Type': 'application/json'}
            token_result = requests.post(authorize_url, data=json.dumps(token_params), headers=token_headers)
            token_json = token_result.json()
            if token_json["token"]:
                token = token_json["token"]
                authorized_headers = {"Authorization": f"Bearer {token}"}
                worksheet_slug = '|'.join(worksheet_names)
                result = requests.get(f"{url}?spreadsheet_id={spreadsheet_id}&worksheet_names={worksheet_slug}&external_use_s3={store_in_s3}&bypass_cache={bypass_cache}", headers=authorized_headers)
                result_json = result.json()
    
        if result_json is not None:
            if "customized" in result_json:
                output = json.dumps(result_json, default=str)
            else:
                races = result_json["Races"]
                candidates = result_json["Candidates"]

                if races is not None:
                    data["races"] = []
                    for race in races:
                        race = format_race(race)
                        # add to the returnable data
                        if race != None:
                            data["races"].append(race)

                if candidates is not None:
                    data["candidates"] = []
                    for candidate in candidates:
                        candidate = format_candidate(candidate, 'house', races)
                        # add to the returnable data
                        if candidate != None:
                            data["candidates"].append(candidate)
                
                # set metadata and send the customized json output to the api
                if "generated" in result_json:
                    data["generated"] = result_json["generated"]
                data["customized"] = datetime.datetime.now()
                if cache_timeout != 0:
                    data["cache_timeout"] = data["customized"] + timedelta(seconds=int(cache_timeout))
                else:
                    data["cache_timeout"] = 0
                output = json.dumps(data, default=str)
                
            if "customized" not in result_json or store_in_s3 == "true":
                overwrite_url = current_app.config["OVERWRITE_API_URL"]
                params = {
                    "spreadsheet_id": spreadsheet_id,
                    "worksheet_names": worksheet_names,
                    "output": output,
                    "cache_timeout": cache_timeout,
                    "bypass_cache": "true",
                    "external_use_s3": store_in_s3
                }

                headers = {'Content-Type': 'application/json'}
                if authorized_headers:
                    headers = headers | authorized_headers
                result = requests.post(overwrite_url, data=json.dumps(params), headers=headers)
                result_json = result.json()
                if result_json is not None:
                    output = json.dumps(result_json, default=str)

    else:
        output = {} # something for empty data
    return output


def format_race(race):
    # add the office id
    if race["office"] != None:
        race["region-id"] = slugify(race["region"], to_lower=True)
        race["office-id"] = slugify(race["office"], to_lower=True)
        race["chamber"] = get_chamber(race["office-id"])
        race["district"] = get_district(race["office-id"])
        # add the party id for the previous election numbers
        if race["2016-20-comp"].find("D") != -1:
            race["2016-20-party-id"] = slugify("DFL", to_lower=True)
        elif race["2016-20-comp"].find("R") != -1:
            race["2016-20-party-id"] = slugify("Republican", to_lower=True)
        if race["2020-pres"].find("D") != -1:
            race["2020-pres-party-id"] = slugify("DFL", to_lower=True)
        elif race["2020-pres"].find("R") != -1:
            race["2020-pres-party-id"] = slugify("Republican", to_lower=True)
        if race["2016-pres"].find("D") != -1:
            race["2016-pres-party-id"] = slugify("DFL", to_lower=True)
        elif race["2016-pres"].find("R") != -1:
            race["2016-pres-party-id"] = slugify("Republican", to_lower=True)
        # add expenditures
        if race["expenditures-dfl"]:
            race["expenditures-dfl"] = "{:0,.2f}".format(float(race["expenditures-dfl"]))
        if race["expenditures-republican"]:
            race["expenditures-republican"] = "{:0,.2f}".format(float(race["expenditures-republican"]))
    else:
        race = None
        
    return race


def format_candidate(candidate, chamber, races):

    # set up candidate
    if candidate["office-sought"] != None and candidate["name"] != None:

        # make an ID
        candidate_id = candidate["office-sought"].replace(" ", "").lower() + "-" + candidate["name"].replace(" ", "").lower()
        candidate["candidate-id"] = candidate_id
        
        # add the office for this candidate
        race_key = [k for k, race in enumerate(races) if race["office"] == candidate["office-sought"]][0]
        candidate["race-id"] = slugify(races[race_key]["office"], to_lower=True)
        candidate["chamber"] = get_chamber(candidate["race-id"])

        # add the party id
        if candidate["party"] != None:
            candidate["party-id"] = slugify(candidate["party"], to_lower=True)
        # format the boolean fields
        candidate["incumbent"] = convert_xls_boolean(candidate["incumbent"])
        candidate["endorsed"] = convert_xls_boolean(candidate["endorsed"])
    else:
        candidate = None
        
    return candidate


def get_district(race_id):
    if race_id.find("senate") != -1:
        district = race_id.replace('senate-district-', '')
    else:
        district = race_id.replace('house-district-', '')
        district = str(district).zfill(3)
    return district


def get_chamber(race_id):
    if race_id.find("senate") != -1:
        chamber = "Senate"
    else:
        chamber = "House"
    return chamber


def convert_xls_boolean(string):
    if string == None:
        value = False
    else:
        string = string.lower()
        if string == "yes" or string == "true" or string == "y":
            value = True
        elif string == "no" or string == "false" or string == "n":
            value = False
        else:
            value = bool(string)
    return value
