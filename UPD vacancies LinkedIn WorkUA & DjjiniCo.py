from collections import defaultdict
from bs4 import BeautifulSoup
import plotly.graph_objects as go
import warnings, re, json
from tqdm import tqdm
import requests
from requests.exceptions import HTTPError, ConnectionError, Timeout, RequestException
import pandas as pd
from datetime import datetime, timedelta
import tldextract
# Suppress warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)
total_quantity_all_positions = defaultdict(int)  # Declare the variable here

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
    total_positions_all_data = defaultdict(lambda: defaultdict(int))
    total_positions_all_keywords_data = defaultdict(lambda: defaultdict(int))
    total_iterations = (end_date - start_date).days + 1
    current_date = start_date
    with tqdm(total=total_iterations, desc=f"Analyzing {website_url}", unit="day") as pbar:
        while current_date <= end_date:
            timestamp = current_date.strftime("%Y%m%d")
            archived_html = get_archived_html(website_url, timestamp)
            positions = []  # Initialize positions outside the try block

            if archived_html:
                try:
                    soup = BeautifulSoup(archived_html, 'html.parser')

                    if 'work.ua' in website_url:
                        positions = soup.find_all('h2', class_='')
                    elif 'djinni.co' in website_url:
                        if current_date >= datetime(2023, 8, 17):
                            positions = soup.find_all('div', class_='job-list-item')
                        else:
                            positions = soup.find_all('li', class_='list-jobs__item')  
                    elif 'linkedin.com' in website_url:
                        job_listings = soup.find_all("div", class_="base-card relative w-full hover:no-underline focus:no-underline base-card--link base-search-card base-search-card--link job-search-card")
                        for job in job_listings:
                            title_container = job.find("h3", class_="base-search-card__title")
                            if title_container:
                                job_title = title_container.text.strip()
                                if job_title:
                                    positions.append(job_title)
                    else:
                        raise ValueError(f"Unsupported website: {website_url}")

                    total_positions_all_keywords = 0
                    total_positions_all = 0
                    total_positions = 0
                    positions_with_keyword_count=0
                    percentage=0

                    for keyword in keywords:
                        if 'work.ua' in website_url:
                            positions_with_keyword = {position.a.get_text().lower() for position in positions if position.a and keyword.lower() in position.a.get_text().lower()}
                        elif 'linkedin.com' in website_url:
                            positions_with_keyword = {position.lower() for position in positions if keyword.lower() in position.lower()}
                        elif 'djinni.co' in website_url:
                            positions_with_keyword = {position.text.lower() for position in positions if keyword.lower() in position.text.lower()}
                        else:
                            positions_with_keyword = set()

                        total_positions = len(positions_with_keyword)
                        total_positions_all_keywords += total_positions
                        total_quantity_all_positions[(current_date.year, current_date.month, timestamp)] += total_positions

                    for keyword in keywords:
                        if 'work.ua' in website_url:
                            positions_with_keyword = set(position.a.get_text().lower() for position in positions if
                                                        position.a and keyword.lower() in position.a.get_text().lower())
                        elif 'linkedin.com' in website_url:
                            positions_with_keyword = set(position.lower() for position in positions if 
                                                         keyword.lower() in position.lower())
                        elif 'djinni.co' in website_url:
                            positions_with_keyword = set(position.text.lower() for position in positions if
                                                        keyword.lower() in position.text.lower())
                        else:
                            positions_with_keyword = set()
                            
                        total_positions_all = len(positions) #all pavailable positions
                        total_positions_all_data[website_url][timestamp] = total_positions_all
                        total_positions_all_keywords_data[website_url][timestamp] = total_positions_all_keywords
                        
                        total_positions = len(positions_with_keyword)
                        positions_with_keyword_count = len(positions_with_keyword)

                        percentage = (positions_with_keyword_count / total_positions_all_keywords) * 100 if total_positions_all_keywords > 0 else 0

                        position_percentage_data[website_url][keyword][(current_date.year, current_date.month, timestamp)] = {
                            'percentage': percentage,
                            'quantity': total_positions,
                            'total_positions_all_keywords': total_positions_all_keywords,
                            'total_quantity_all_positions': total_quantity_all_positions[(current_date.year, current_date.month, timestamp)]
                        }
                    pbar.update(1)

                except Exception as e:
                    print(f"Error processing {website_url} at {timestamp}: {str(e)}")

            current_date += timedelta(days=1)

        position_percentage_data['total_positions_all'] = total_positions_all_data
        position_percentage_data['total_positions_all_keywords'] = total_positions_all_keywords_data
    return position_percentage_data  


def create_chart(position_percentage_data, start_date, end_date, output_file="position_chart.html"):
    fig = go.Figure()
    max_percentage = 0
    total_days = 0

    # Gather all unique dates from all websites
    all_dates_set = {date[2] for website_data in position_percentage_data.values() for keyword_data in website_data.values() for date, values in keyword_data.items() if isinstance(values, dict) and values.get('quantity', 0) > 0}
    all_dates = sorted(list(all_dates_set))
    legend_entries = set()

    # Create a dictionary to store aggregated data for each keyword on each date
    aggregated_data = defaultdict(lambda: defaultdict(float))
    all_percentages = []

    for website_url, website_data in position_percentage_data.items():
        total_positions_all_keywords = 0
        total_quantity_all_positions = defaultdict(int)

        for keyword, data in website_data.items():
            total_positions_all = total_quantity = total_percentage = keyword_days = 0
            date_data_dict = defaultdict(
                lambda: {'quantity': 0, 'percentage': 0, 'total_positions_all_keywords': 0,
                         'total_quantity_all_positions': 0, 'total_positions_all': 0})

            for key, values in data.items():
                if isinstance(values, int) and values > 0:
                    total_quantity += values
                    total_positions_all += values
                elif isinstance(values, dict) and values.get('quantity', 0) > 0:
                    total_quantity += values.get('quantity', 0)
                    total_positions_all += values.get('total_positions_all', 0)

                    if isinstance(values, dict):
                        total_positions_all_keywords = max(total_positions_all_keywords,
                                                            values.get('total_positions_all_keywords', 0))
                        total_quantity_all_positions[key[2]] = values.get('total_quantity_all_positions', 0) + (values.get('total_positions_all_keywords', 0) - values.get('quantity', 0))

                        #max_percentage = max(max_percentage, values['percentage'])

                        total_days += 1
                        if values['percentage'] > 0:
                            keyword_days += 1
                            total_percentage += values['percentage']
                            
                        all_percentages.append(values['percentage'])
                            
                        date_data_dict[key[2]] = {
                            'current': values.get('quantity', 0),
                            'total_quantity': total_quantity,
                            'percentage': values['percentage'],
                            'total_positions_all_keywords': values.get('total_positions_all_keywords', 0),
                            'total_quantity_all_positions': values.get('total_quantity_all_positions', 0),
                            'total_positions_all': values.get('total_positions_all', 0)
                        }
            max_percentage = max(all_percentages, default=0)
                
            average_percentage = total_percentage / keyword_days if keyword_days > 0 else 0
            sorted_data = sorted(date_data_dict.items(), key=lambda item: item[0])

            if sorted_data:
                for date, values in sorted_data:
                    aggregated_data[keyword][date] += values['percentage']

                # Create x and y values for the trace
                x_values_dates, y_values_percentage = zip(*[(date, aggregated_data[keyword][date]) for date, _ in sorted_data])

                hover_text = [
                    f'  Date: {date}<br>'
                    f'  Current Quantity:{values["current"]}<br>'
                    f'  Current Percentage: {values["percentage"]:.2f}%<br>'
                    f'  Total Quantity: {values["total_quantity"]}<br>'
                    f'  Total Keywords: {values["total_positions_all_keywords"]}<br>'
                    f'  All Positions: {values["total_quantity_all_positions"]}<br>'
                    for date, values in sorted_data
                ]
                extracted_info = tldextract.extract(website_url)
                domain_name = f"{extracted_info.domain}.{extracted_info.suffix}"
                legend_entry = (f"{keyword}-{average_percentage:.2f}%<br>{domain_name}", average_percentage)
                if legend_entry not in legend_entries:
                    trace_percentage = go.Scatter(
                        x=x_values_dates,
                        y=y_values_percentage,
                        stackgroup='one',
                        name=f"{keyword}-{average_percentage:.2f}%<br>{domain_name}",
                        hovertemplate=hover_text,
                        text=x_values_dates,
                        connectgaps=False,
                        mode='markers+lines',  # Set mode to 'markers+lines' to show markers
                        marker=dict(size=3),  # Adjust the marker size here (e.g., size=5)
                    )

                    fig.add_trace(trace_percentage)
                    legend_entries.add(legend_entry)

    fig.update_layout(
        legend=dict(
            title='Key Words',
            traceorder='reversed',
            itemsizing='constant',
            tracegroupgap=0,
            borderwidth=0,
        ),
        title=f'Key Words in Opened Vacancies ({start_date.strftime("%b %d, %Y")} - {end_date.strftime("%b %d, %Y")})',
        yaxis_title='%',
        template='plotly_dark',
        xaxis=dict(type='category', categoryorder='array', categoryarray=sorted(all_dates)),
        yaxis_range=[0, max_percentage+1],
    )

    fig.write_html(output_file)
    print(f"Chart saved to {output_file}")

def export_to_excel(position_percentage_data, output_file="position_data.xlsx"):
    result_data = defaultdict(list)

    for website_url, keyword_data in position_percentage_data.items():
        for keyword, data in keyword_data.items():
            for key, values in data.items():
                if isinstance(values, dict):
                    timestamp = key[2]
                    timestamp_str = str(timestamp)
                    date_info = datetime.strptime(timestamp_str, "%Y%m%d")  # Correct the timestamp format
                    result_data['Website'].append(website_url)
                    result_data['Keyword'].append(keyword)
                    result_data['Quantity'].append(values.get('quantity', 0))
                    result_data['Percentage'].append(values.get('percentage', 0))
                    result_data['Total_Positions_All_Keywords'].append(values.get('total_positions_all_keywords', 0))
                    result_data['Total_Quantity_All_Positions'].append(values.get('total_quantity_all_positions', 0))
                    result_data['Date'].append(date_info.strftime('%Y-%m-%d'))  # Adding the formatted date

    df = pd.DataFrame(result_data)
    df.to_excel(output_file, index=False)
    print(f"Data exported to {output_file}")

def main():
    keywordslist=["Analyst", "Developer", "Manager", "Cloud", "QA", "Lead", "Talent", "HR","Recruiter"]
    #keywordsua=["Analyst", "Developer", "Manager", "Cloud", "QA", "Lead", "HR","Recruiter","Talent",
    #                                 "Аналітик", "Розробник", "Менеджер", "Тестувальник", "Керівник"]
    keywordsua=["Chief","Senior", "Middle", "Junior", "Intern", "Internship","Головний","Старший","Молодший"]

    websites = {
        'https://work.ua/jobs-it/': keywordsua,
        'https://djinni.co/jobs/': keywordsua,
        'https://www.linkedin.com/jobs/search/?keywords={job_title}&location={Ukraine}': keywordsua
    }

    start_date = datetime(2023, 1, 1)
    end_date = datetime(2023, 12, 31)

    position_percentage_data = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for website_url, keywords in websites.items():
        print(f"\nAnalyzing {website_url}...")
        position_percentage_data.update(analyze_position_percentage(website_url, keywords, start_date, end_date))

    create_chart(position_percentage_data, start_date, end_date, output_file="combined_position_chart.html")
    export_to_excel(position_percentage_data, output_file="combined_position_data.xlsx")

if __name__ == "__main__":
    main()
