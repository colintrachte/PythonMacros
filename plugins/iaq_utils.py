# plugins/gcode_utils.py

import re
import csv
import io

def process_sensor_data(lines):
    """
    Standardized plugin: Converts raw sensor log lines into a CSV formatted list of lines.
    """
    # Regex 1: Identifies the start of a record and captures until the next date
    record_regex = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(.*?)(?=\d{4}-\d{2}-\d{2}|\Z)", re.DOTALL)
    
    # Regex 2: Extracts Key: Value pairs
    kv_regex = re.compile(r"(\w+[\.\d]*):\s*([\d\.]+\w*/?\w*%?)")

    # Combine input lines into one string for regex finditer
    content = "".join(lines)
    
    data_rows = []
    all_keys = set(["Timestamp"])

    for match in record_regex.finditer(content):
        row = {"Timestamp": match.group(1)}
        measurements = kv_regex.findall(match.group(2))
        
        for k, v in measurements:
            row[k] = v
            all_keys.add(k)
        
        # FILTER: Only keep the row if it reached the 'HUMIDITY' marker
        if "HUMIDITY" in row:
            data_rows.append(row)

    # Define header order: Timestamp first, then alphabetically
    header = ["Timestamp"] + sorted([k for k in all_keys if k != "Timestamp"])

    # Use io.StringIO to "write" the CSV to a string buffer instead of a file
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=header)
    writer.writeheader()
    writer.writerows(data_rows)

    # Return the CSV content as a list of lines to remain compatible with app.py
    return output.getvalue().splitlines(keepends=True)