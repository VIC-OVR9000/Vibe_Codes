import plotly.express as px
import pandas as pd
import itertools
import ipywidgets as widgets
from IPython.display import display

# Initial Data
lease_data = {
    15: 940, 14: 941, 13: 942, 12: 943, 11: 1031, 10: 1185, 
    9: 1200, 8: 1219, 7: 1244, 6: 1279, 5: 1328, 4: 1404, 3: 1536
}

# UI Elements
term_input = widgets.IntText(value=12, description="Term (mo):")
price_input = widgets.IntText(value=950, description="Price ($):")
add_button = widgets.Button(description="Update Data", button_style='info')

# Output areas
chart_output = widgets.Output()
table_output = widgets.Output()

def render(data):
    # Prepare Plot
    combinations = []
    for (dur_a, price_a), (dur_b, price_b) in itertools.product(data.items(), repeat=2):
        combinations.append({
            "Lease A": str(dur_a),
            "Total Months": dur_a + dur_b,
            "Avg Monthly": ((dur_a * price_a) + (dur_b * price_b)) / (dur_a + dur_b),
            "Sequence": f"{dur_a}+{dur_b}",
        })
    df = pd.DataFrame(combinations)
    fig = px.line(df, x="Total Months", y="Avg Monthly", color="Lease A", 
                  markers=True, template="plotly_white",hover_data=["Sequence"])
    
    fig.update_layout(title="MARKET ANALYSIS: DYNAMIC LEASE EFFICIENCY",
                      font=dict(family="Courier New, monospace"),
                      plot_bgcolor="white", paper_bgcolor="white")
    fig.update_xaxes(showgrid=True, gridcolor='black')
    fig.update_yaxes(showgrid=True, gridcolor='black')

    # Prepare Table
    df_table = pd.DataFrame(list(data.items()), columns=['Term (Months)', 'Monthly Rent ($)'])
    df_table = df_table.sort_values(by='Term (Months)', ascending=False)

    with chart_output:
        chart_output.clear_output()
        fig.show()
    with table_output:
        table_output.clear_output()
        display(df_table.style.hide(axis='index'))

def on_click(b):
    lease_data[term_input.value] = price_input.value
    render(lease_data)

add_button.on_click(on_click)
display(widgets.VBox([widgets.HBox([term_input, price_input, add_button]), 
                      widgets.HBox([chart_output, table_output])]))

# Initial Render
render(lease_data)
