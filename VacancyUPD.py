from collections import defaultdict
from bs4 import BeautifulSoup
import plotly.graph_objects as go
import warnings
from tqdm import tqdm  # Import tqdm for progress bar
import requests
from requests.exceptions import HTTPError, ConnectionError, Timeout, RequestException
import pandas as pd
from datetime import datetime, timedelta

# Suppress warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

def get_archived_html(website_url, timestamp, max_retries=3):
    for attempt in range(max_retries):
        try:
            print(f"Retrieving data for {website_url} at {timestamp}...")
            wayback_url = f"http://web.archive.org/web/{timestamp}/{website_url}"
            response = requests.get(wayback_url, timeout=10)
            response.raise_for_status()
            print("Data retrieved successfully.")
            return response.text

        except HTTPError as errh:
            if response.status_code == 404:
                print(f"Error 404: {wayback_url} not found.")
            else:
                print(f"HTTP Error: {errh}")

        except ConnectionError as errc:
            warnings.warn(f"Error Connecting: {errc}", RuntimeWarning)

        except Timeout as errt:
            print(f"Timeout Error: {errt}")

        except RequestException as err:
            print(f"An error occurred: {err}")

        print(f"Retrying... (Attempt {attempt + 1}/{max_retries})")

    print(f"Max retries ({max_retries}) exceeded. Unable to retrieve data.")
    return None


def analyze_position_percentage(website_url, keywords, start_date, end_date):
    position_percentage_data = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    total_iterations = (end_date - start_date).days + 1
    current_date = start_date
    with tqdm(total=total_iterations, desc=f"Analyzing {website_url}", unit="day") as pbar:
        while current_date <= end_date:
            timestamp = current_date.strftime("%Y%m%d")
            archived_html = get_archived_html(website_url, timestamp)

            if archived_html:
                try:
                    soup = BeautifulSoup(archived_html, 'html.parser')

                    if current_date >= datetime(2023, 8, 17):
                        positions = soup.find_all('div', class_='job-list-item')  # Adjust for new structure
                    else:
                        positions = soup.find_all('li', class_='list-jobs__item')  # Adjust for old structure

                    for keyword in keywords:
                        total_positions = len(positions)
                        positions_with_keyword = sum(1 for position in positions if keyword.lower() in position.text.lower())

                        percentage = (positions_with_keyword / total_positions) * 100 if total_positions > 0 else 0

                        # Store 'quantity' in the dictionary
                        position_percentage_data[website_url][keyword][(current_date.year, current_date.month, timestamp)] = {
                            'percentage': percentage,
                            'quantity': positions_with_keyword
                        }

                    # Increment the progress bar
                    pbar.update(1)

                except Exception as e:
                    print(f"Error processing {website_url} at {timestamp}: {str(e)}")

            current_date += timedelta(days=1)

    return position_percentage_data

def create_chart(position_percentage_data, start_date, end_date, output_file="position_chart.html"):
    fig = go.Figure()

    legend_entries = []  # Store legend entries for sorting

    max_percentage = 0  # Initialize max_percentage
    total_days = 0  # Initialize total_days outside the loop

    for website_url, keyword_data in position_percentage_data.items():
        for keyword, data in keyword_data.items():
            total_quantity = 0
            total_percentage = 0  # Initialize total_percentage for each keyword
            keyword_days = 0  # Initialize keyword_days for each keyword

            sorted_data = []

            for key, values in data.items():
                total_quantity += values['quantity']
                max_percentage = max(max_percentage, values['percentage'])  # Update max_percentage directly

                # Increment the total number of days and keyword_days
                total_days += 1
                if values['percentage'] > 0:  # Only consider days with non-zero percentage
                    keyword_days += 1
                    total_percentage += values['percentage']  # Accumulate the total percentage for the keyword

                sorted_data.append((key, values))

            # Calculate the average percentage for the current keyword
            average_percentage = total_percentage / keyword_days if keyword_days > 0 else 0  # Use keyword_days for the average calculation

            sorted_data = sorted(sorted_data, key=lambda item: item[1]['percentage'], reverse=True)
            x_values_dates = [f"{key[2]}" for key, values in sorted_data]

            if sorted_data:
                x_values = [f"{key[0]}-{key[2]}" for key, values in sorted_data]
                y_values_percentage = [values['percentage'] for key, values in sorted_data]

                hover_text = []
                for key, values in sorted_data:
                    hover_text.append(f'Date: {key[2]}<br>Quantity: {values["quantity"]}<br>Percentage: {values["percentage"]:.2f}%')

                # Create a single trace for each keyword with the entire set of values
                trace_percentage = go.Scatter(
                    x=x_values_dates,
                    y=y_values_percentage,
                    stackgroup='one',  # Add this line for stacking
                    name=f"{keyword} <br>({average_percentage:.2f}%)",  # Use the actual calculated average_percentage
                    hovertemplate=f'Total: {total_quantity}<br>' +
                                  f'Current: {sorted_data[0][1]["quantity"]} <br>' +
                                  'Date: %{text}',
                    text=x_values_dates,
                    hovertext=hover_text,
                    connectgaps=False,  # This option prevents connecting lines for missing values
                )
                fig.add_trace(trace_percentage)
                legend_entries.append((f"{keyword} ({average_percentage:.2f}%)", average_percentage))

    fig.update_layout(
        legend=dict(
            title='Key Words',
            traceorder='reversed',
            itemsizing='constant',
            tracegroupgap=0,
            borderwidth=0,
        ),
        title=f'Key Words in Opened Vacancies ({start_date.strftime("%b %d, %Y")} - {end_date.strftime("%b %d, %Y")}) on {website_url}',
        xaxis_title='',
        yaxis_title='%',
        template='plotly_dark',
        xaxis=dict(type='category', categoryorder='array', categoryarray=x_values_dates),
        yaxis_range=[0, max_percentage],  # Set the y-axis range to be between 0 and the maximum percentage
    )

    fig.write_html(output_file)
    print(f"Chart saved to {output_file}")


def export_to_excel(position_percentage_data, output_file="position_data.xlsx"):
    result_data = defaultdict(list)

    for website_url, keyword_data in position_percentage_data.items():
        for keyword, percentage_data in keyword_data.items():
            for key in sorted(percentage_data.keys()):
                result_data['Year'].append(key[0])
                result_data['Timestamp'].append(key[2])
                result_data['Percentage'].append(percentage_data[key]['percentage'])
                result_data['Quantity'].append(percentage_data[key]['quantity'])
                result_data['Website'].append(website_url)
                result_data['Keyword'].append(keyword)

    result_df = pd.DataFrame(result_data)
    result_df.to_excel(output_file, index=False)
    print(f"Data exported to {output_file}")

def main():
    websites = ['https://djinni.co/jobs/']
    #skeywords = ["Analyst", "Developer", "Manager", "Cloud", "QA", "Lead", "HR"]
    keywords = ["Senior", "Middle", "Junior", "Internship"]

    start_date = datetime(2023, 1, 1)
    end_date = datetime(2023, 12, 21)

    position_percentage_data = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for website_url in websites:
        print(f"\nAnalyzing {website_url}...")
        position_percentage_data.update(analyze_position_percentage(website_url, keywords, start_date, end_date))

    create_chart(position_percentage_data, start_date, end_date)
    export_to_excel(position_percentage_data)

if __name__ == "__main__":
    main()