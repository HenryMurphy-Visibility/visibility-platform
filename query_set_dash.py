from dash import Dash, dcc, html, Input, Output, State
import pandas as pd
import plotly.graph_objects as go

# Sample Data (replace with your actual query set data)
data = pd.DataFrame({
    'investment': ['A', 'B', 'C', 'A', 'B', 'C'],
    'location': ['Goldman', 'NY', 'London', 'Goldman', 'NY', 'London'],
    'ls': ['net', 'long', 'short', 'net', 'long', 'short'],
    'quantity': [100, 200, 300, 150, 250, 350],
    'price': [1.2, 1.3, 1.4, 1.5, 1.6, 1.7],
})

# Create a Dash application
app = Dash(__name__)

# Layout of the application
app.layout = html.Div([
    html.H1("Query Set Dashboard"),

    # Dimension selection
    html.Label("Select Dimensions:"),
    dcc.Checklist(['investment', 'location', 'ls'], id="dimension-select", inline=True),

    # Metric selection
    html.Label("Select Metric:"),
    dcc.Dropdown(['quantity', 'price', 'MktVal'], id="metric-select"),

    # Filter inputs
    html.Label("Location Filter:"),
    dcc.Input(id="location-filter", type="text", placeholder="e.g., Goldman"),

    # Execute button
    html.Button("Execute Query", id="execute-query"),

    # Display table and chart
    dcc.Graph(id="result-table"),
])


# Function to calculate Market Value
def calculate_mkt_val(data):
    data['MktVal'] = data['quantity'] * data['price']
    return data


# Callback to update results based on selected query
@app.callback(
    Output("result-table", "figure"),
    [Input("dimension-select", "value"),
     Input("metric-select", "value"),
     Input("execute-query", "n_clicks")],
    State("location-filter", "value")
)
def update_table(dimensions, metric, n_clicks, location_filter):
    if n_clicks is None:
        return {}

    # Apply Market Value calculation if 'MktVal' is selected
    if metric == 'MktVal':
        data_with_mkt_val = calculate_mkt_val(data.copy())
    else:
        data_with_mkt_val = data.copy()

    # Apply filter if specified
    if location_filter:
        data_with_mkt_val = data_with_mkt_val[data_with_mkt_val['location'] == location_filter]

    # Aggregate data based on selected dimensions and metric
    agg_data = data_with_mkt_val.groupby(dimensions).agg({metric: 'sum'}).reset_index()

    # Convert to table format for display
    fig = go.Figure(data=[go.Table(
        header=dict(values=list(agg_data.columns)),
        cells=dict(values=[agg_data[col] for col in agg_data.columns])
    )])

    return fig


if __name__ == '__main__':
    app.run_server(debug=True)
