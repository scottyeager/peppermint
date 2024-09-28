from datetime import datetime
import urllib.parse
import requests
from fasthtml.common import *
import grid3.network

mainnet = grid3.network.GridNetwork()
app, rt = fast_app(live=True)

# Keep a cache of known receipts, keyed by hash. Ideally we'd also keep record of which node ids have been queried and when, to know if there's a possibility of more receipts we didn't cache yet
receipts = {}

@rt("/")
def get():
    return render_main()

@rt("/{select}/{id_input}")
@rt("/{select}/{id_input}/{filter_option}")
def get(req, select: str, id_input: int, filter_option: str = None):
    if select == "node":
        results = [render_receipts(id_input)]
    elif select == "farm":
        nodes = mainnet.graphql.nodes(["nodeID"], farmID_eq=id_input)
        node_ids = sorted([node["nodeID"] for node in nodes])
        results = []
        if filter_option == "nodes":
            for node in node_ids:
                results.append(H2(f"Node {node}"))
                results.append(render_receipts(node))
        elif filter_option == "periods":
            # Implement period filtering logic here
            results.append(H2("Period filtering not implemented yet"))
        else:
            # Default behavior when no filter is selected
            for node in node_ids:
                results.append(H2(f"Node {node}"))
                results.append(render_receipts(node))

    has_result = False
    for result in results:
        if result:
            has_result = True

    if not has_result:
        results = "No receipts found."

    if "hx-request" in req.headers:
        return results
    else:
        return render_main(select, id_input, results, filter_option)

@rt("/node/{node_id}/{rhash}")
def get(node_id: int, rhash: str):
    details = render_details(rhash)

    # Details can be an error which is a string. Also the receipt might not be cached before we call render_details above. This whole thing is kinda ugly... TODO: refactor the caching and error handling
    if type(details) is not str:
        if receipts[rhash]["node_id"] != node_id:
            details = "Hash doesn't match node id"

    return render_main(id_input=node_id, result=details)

@rt("/details")
def get(rhash: str):
    return render_details(rhash)

def process_receipt(receipt):
    # Flatten receipts so the type is an attribute
    if "Minting" in receipt:
        r = receipt["Minting"]
        r["type"] = "Minting"
    elif "Fixup" in receipt:
        r = receipt["Fixup"]
        r["type"] = "Fixup"
    return r

def render_details(rhash):
    if rhash not in receipts:
        response = requests.get(
            f"https://alpha.minting.tfchain.grid.tf/api/v1/receipt/{rhash}"
        )
        if not response.ok:
            return "Hash not found"
        else:
            receipts[rhash] = process_receipt(response.json())

    receipt = receipts[rhash]
    return [
        H2(f"Node {receipt['node_id']} Details"),
        Table(
            receipt_header(),
            render_receipt(rhash, receipt, False),
            *render_receipt_row2(receipt),
        ),
    ]

def render_main(select="node", id_input=None, result="", filter_option=None):
    farm_selected = select == "farm"
    return Titled(
        "Fetch Minting Receipts",
        Form(
            hx_get=f"/{select}/{id_input}",
            hx_push_url=f"/{select}/{id_input}",
            hx_target="#result",
            hx_trigger="submit",
            onsubmit="document.getElementById('result').innerHTML = 'Loading...'",
            oninput="""
                    const sel = this.elements.select.value;
                    const id = this.elements.id_input.value;
                    const filter = this.elements.filter_select ? this.elements.filter_select.value : '';
                    const path = '/' + sel + '/' + id + (filter ? '/' + filter : '');
                    this.setAttribute('hx-get', path);
                    this.setAttribute('hx-push-url', path);
                    htmx.process(this);
                    // Setting `value` and `selected` help make the form data persistent when using the browser back button.
                    this.elements.id_input.setAttribute('value', id)
                    for (child of this.elements.select.children){
                        if (child.value == sel) {
                            child.setAttribute('selected', 'selected')
                        } else {
                            child.removeAttribute('selected')
                        }
                    }
                    if (this.elements.filter_select) {
                        for (child of this.elements.filter_select.children){
                            if (child.value == filter) {
                                child.setAttribute('selected', 'selected')
                            } else {
                                child.removeAttribute('selected')
                            }
                        }
                    }
                    this.elements.id_input.getAttribute('value')
                    """,
        )(
            Div(
                Div(
                    Input(
                        type="number",
                        id="id_input",
                        placeholder=42,
                        value=id_input,
                        required="true",
                    ),
                    style="display: inline-block",
                ),
                Div(
                    Select(
                        Option("Node ID", value="node", selected=select == "node"),
                        Option("Farm ID", value="farm", selected=select == "farm"),
                        id="select",
                        onchange="toggleFilterOptions(this.value)"
                    ),
                    style="display: inline-block",
                ),
                Div(
                    Select(
                        Option("Filter by Node IDs", value="nodes", selected=filter_option == "nodes"),
                        Option("Filter by Periods", value="periods", selected=filter_option == "periods"),
                        id="filter_select",
                        style="display: none" if not farm_selected else "inline-block"
                    ),
                    style="display: inline-block",
                ),
                Div(
                    Button("Go", type="submit"),
                    style="display: inline-block",
                ),
            ),
            # CheckboxX(id="fixups", label="Show fixups"),
        ),
        Br(),
        Div(*result, id="result"),
        Style(
            """
            table tr:hover td {
            background: #efefef;
            cursor: pointer;
            }
            """
        ),
        Script("""
            function toggleFilterOptions(value) {
                var filterSelect = document.getElementById('filter_select');
                if (value === 'farm') {
                    filterSelect.style.display = 'inline-block';
                } else {
                    filterSelect.style.display = 'none';
                }
            }
        """)
    )

def render_receipts(node_id):
    if node_id:
        try:
            node_id = int(node_id)
        except ValueError:
            return "Please enter a valid node id"
    else:
        return "Please enter a valid node id"

    try:
        response = requests.get(
            f"https://alpha.minting.tfchain.grid.tf/api/v1/node/{node_id}"
        ).json()
    except requests.exceptions.JSONDecodeError:
        return None

    rows = [receipt_header()]
    for receipt in response:
        rhash, receipt = receipt["hash"], receipt["receipt"]
        receipt = process_receipt(receipt)
        if rhash not in receipts:
            receipts[rhash] = receipt
        if receipt["type"] == "Minting":
            rows.append(render_receipt(rhash, receipt))
    return Table(*rows)

def render_receipt(rhash, r, details=True):
    uptime = round(r["measured_uptime"] / (30.45 * 24 * 60 * 60) * 100, 2)
    if details:
        row = Tr(
            hx_get="/details",
            hx_target="#result",
            hx_trigger="click",
            hx_vals={"rhash": rhash},
            hx_push_url=f"/node/{r['node_id']}/{rhash}",
        )
    else:
        row = Tr()
    return row(
        Td(datetime.fromtimestamp(r["period"]["start"]).date()),
        Td(datetime.fromtimestamp(r["period"]["end"]).date()),
        Td(f"{uptime}%"),
        Td(r["reward"]["tft"] / 1e7),
    )

def render_receipt_row2(r):
    return [
        Tr(
            Th(Br(), Strong("CU")),
            Th(Br(), Strong("SU")),
            Th(Br(), Strong("NU")),
            Th(Br(), Strong("Certification")),
        ),
        Tr(
            Td(r["cloud_units"]["cu"]),
            Td(r["cloud_units"]["su"]),
            Td(r["cloud_units"]["nu"]),
            Td(r["node_type"]),
        ),
    ]

def receipt_header():
    return Tr(
        Th(Strong("Period Start")),
        Th(Strong("Period End")),
        Th(Strong("Uptime")),
        Th(Strong("TFT Minted")),
    )

serve()