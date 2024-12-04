import folium
from jinja2 import Template
import requests
import base64
from urllib.parse import urlparse, parse_qs
import json
from shapely.geometry import LineString, Polygon
from shapely.ops import transform
from pyproj import Transformer

def fetch_image_data_uri(url):
    response = requests.get(url)
    if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            data = base64.b64encode(response.content).decode('utf-8')
            return f'data:{content_type};base64,{data}'
    else:
        return ''

def extract_youtube_video_id(url):
    parsed_url = urlparse(url)
    if parsed_url.hostname == 'youtu.be':
        return parsed_url.path[1:]
    elif parsed_url.hostname in ('www.youtube.com', 'youtube.com'):
        if parsed_url.path == '/watch':
            return parse_qs(parsed_url.query).get('v', [None])[0]
        elif parsed_url.path.startswith('/embed/'):
            return parsed_url.path.split('/')[2]
    return None

def get_youtube_thumbnail_data_uri(video_url):
    video_id = extract_youtube_video_id(video_url)
    if video_id:
        thumbnail_url = f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'
        return fetch_image_data_uri(thumbnail_url)
    else:
        return ''

def create_custom_icon(icon_type):
    """Create custom icons based on content type."""
    icon_map = {
        'video': 'video-camera',
        'image': 'camera',
        'text': 'align-left',
        'info-sign': 'info-sign'
    }
    return folium.Icon(
        icon=icon_map.get(icon_type, 'info-sign'),
        prefix='fa',
        color='blue',
        icon_color='#000'
    )

def create_bookmark_content(content):
    """Generate popup content based on content type."""
    if not content:
        return ''
    if content.get('type') == 'video':
        img_data_uri = get_youtube_thumbnail_data_uri(content['url'])
        return f"""
            <div class="modal-content">
                <h3>{content.get('title', '')}</h3>
                <a href="{content['url']}" target="_blank">
                    <img src="{img_data_uri}" alt="{content.get('title', '')}" style="max-width:100%;">
                </a>
                <p>Click the image to watch the video.</p>
            </div>
        """
    elif content.get('type') == 'image':
        img_data_uri = fetch_image_data_uri(content['url'])
        return f"""
            <div class="modal-content">
                <h3>{content.get('title', '')}</h3>
                <img src="{img_data_uri}" alt="{content.get('title', '')}" style="max-width:100%;">
            </div>
        """
    elif content.get('type') == 'text':
        return f"""
            <div class="modal-content">
                <h3>{content.get('title', '')}</h3>
                <p>{content.get('text', '')}</p>
            </div>
        """
    else:
        return ''

def calculate_line_length(coordinates):
    """Calculate the length of a LineString in miles."""
    # Create a LineString object
    line = LineString([(lon, lat) for lon, lat in coordinates])

    # Define a projection to convert lat/lon to meters (Web Mercator)
    transformer = Transformer.from_crs('epsg:4326', 'epsg:3857', always_xy=True)

    # Project the line
    line_projected = transform(transformer.transform, line)

    # Get the length in meters and convert to miles
    length_in_miles = line_projected.length / 1609.34  # meters to miles
    return length_in_miles

def calculate_polygon_area(coordinates):
    """Calculate the area of a Polygon in square miles."""
    # Create a Polygon object
    polygon = Polygon([(lon, lat) for lon, lat in coordinates[0]])

    # Define a projection to convert lat/lon to meters (Web Mercator)
    transformer = Transformer.from_crs('epsg:4326', 'epsg:3857', always_xy=True)

    # Project the polygon
    polygon_projected = transform(transformer.transform, polygon)

    # Get the area in square meters and convert to square miles
    area_in_sq_miles = polygon_projected.area / 2.59e+6  # square meters to square miles
    return area_in_sq_miles

def add_bookmark_to_map(bookmark, m, center):
    geometry = bookmark.get('geometry', {})
    geom_type = geometry.get('type')
    coordinates = geometry.get('coordinates', [])
    tile_layer = bookmark.get('tile_layer', 'Positron')
    title = bookmark.get('title', 'Untitled')
    content = bookmark.get('content', {})
    popup_content = create_bookmark_content(content)
    style = bookmark.get('style', {})
    location = None

    if geom_type == 'Point':
        # Coordinates are [longitude, latitude]
        lon, lat = coordinates
        location = [lat, lon]
        marker = folium.Marker(
            location=location,
            popup=folium.Popup(popup_content, max_width=600),
            icon=create_custom_icon(content.get('type', 'info-sign')),
            tooltip=title
        )
        marker.add_to(m)
    elif geom_type == 'LineString':
        # Coordinates are a list of [longitude, latitude] pairs
        latlngs = [[lat, lon] for lon, lat in coordinates]
        polyline = folium.PolyLine(
            locations=latlngs,
            color=style.get('color', 'blue'),
            weight=style.get('weight', 5),
            opacity=style.get('opacity', 0.7),
            tooltip=title
        )

        # Calculate length
        length_in_miles = calculate_line_length(coordinates)
        length_str = f"Length: {length_in_miles:.2f} miles"

        # Update popup content
        if popup_content:
            popup_content += f"<p>{length_str}</p>"
        else:
            popup_content = f"<div class='modal-content'><h3>{title}</h3><p>{length_str}</p></div>"

        polyline.add_child(folium.Popup(popup_content, max_width=600))
        polyline.add_to(m)

        # Use the midpoint of the line for navigation
        mid_index = len(latlngs) // 2
        location = latlngs[mid_index]
    elif geom_type == 'Polygon':
        # Coordinates are a list of linear rings; we'll use the first ring (outer boundary)
        latlngs = [[lat, lon] for lon, lat in coordinates[0]]
        polygon = folium.Polygon(
            locations=latlngs,
            color=style.get('color', 'red'),
            weight=style.get('weight', 2),
            fill_color=style.get('fillColor', 'red'),
            fill_opacity=style.get('fillOpacity', 0.5),
            tooltip=title
        )

        # Calculate area
        area_in_sq_miles = calculate_polygon_area(coordinates)
        area_str = f"Area: {area_in_sq_miles:.2f} square miles"

        # Update popup content
        if popup_content:
            popup_content += f"<p>{area_str}</p>"
        else:
            popup_content = f"<div class='modal-content'><h3>{title}</h3><p>{area_str}</p></div>"

        polygon.add_child(folium.Popup(popup_content, max_width=600))
        polygon.add_to(m)

        # Use the centroid of the polygon for navigation (approximate)
        lats = [lat for lat, lon in latlngs]
        lons = [lon for lat, lon in latlngs]
        location = [sum(lats)/len(lats), sum(lons)/len(lons)]
    else:
        print(f"Unsupported geometry type: {geom_type}")
        location = center

    return {
        'lat': location[0],
        'lon': location[1],
        'zoom': bookmark.get('zoom', 13),
        'tile_layer': tile_layer
    }

def create_map(bookmarks, center=[39.54316, -110.38948], zoom=3):
    """Create the main map with bookmarks and navigation."""
    # Custom map template to expose the map variable globally
    map_tpl = """
    {% macro header(this, kwargs) %}
        {{ this._parent.render_css() }}
        {{ this._parent.render_js() }}
        {{ this._parent.render_header() }}
    {% endmacro %}

    {% macro html(this, kwargs) %}
        <div class="folium-map" id="{{ this.get_name() }}" ></div>
    {% endmacro %}

    {% macro script(this, kwargs) %}
        var {{ this.get_name() }};
        function init() {
            {{ this.get_name() }} = L.map('{{ this.get_name() }}', {
                center: [{{ this.location[0] }}, {{ this.location[1] }}],
                zoom: {{ this.zoom_start }},
                crs: L.CRS.EPSG3857
            });
            {{ this._parent.render() }}
            // Expose the map variable globally
            window.{{ this.get_name() }} = {{ this.get_name() }};
        }
        document.addEventListener("DOMContentLoaded", init);
    {% endmacro %}
    """

    template = Template(map_tpl)

    m = folium.Map(
        location=center,
        zoom_start=zoom,
        control_scale=True,
        tiles=None  # We'll add tiles explicitly
    )
    m.get_root().template = template

    map_name = m.get_name()

    # Add multiple tile layers with attributions and unique IDs
    tile_layers = {
        'OpenStreetMap': folium.TileLayer(
            'OpenStreetMap',
            name='OpenStreetMap',
            attr='© OpenStreetMap contributors',
            control=True,
            show=False,
            options={'id': 'OpenStreetMap'}
        ),
        'Positron': folium.TileLayer(
            'CartoDB positron',
            name='Positron',
            attr='© OpenStreetMap contributors © CARTO',
            control=True,
            show=True,  # Set as default tile layer
            options={'id': 'Positron'}
        ),
        'Dark Matter': folium.TileLayer(
            'CartoDB dark_matter',
            name='Dark Matter',
            attr='© OpenStreetMap contributors © CARTO',
            control=True,
            show=False,
            options={'id': 'Dark Matter'}
        ),
        'Esri Satellite': folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            name='Esri Satellite',
            attr='Tiles © Esri',
            control=True,
            show=False,
            options={'id': 'Esri Satellite'}
        )
    }

    # Add tile layers to the map
    for tile_name, tile_layer in tile_layers.items():
        tile_layer.add_to(m)

    # Add LayerControl to allow toggling between layers
    folium.LayerControl().add_to(m)

    # Collect locations for navigation
    locations_js = {}
    for i, bookmark in enumerate(bookmarks):
        location_data = add_bookmark_to_map(bookmark, m, center)
        locations_js[i] = location_data

    # Convert locations_js to JSON string
    locations_js_str = json.dumps(locations_js)

    # JavaScript code for navigation and copying coordinates
    nav_js = """
    <script>
    function initMapFunctions() {{
        const locations = {locations_js};

        var tileLayers = {{}};

        {map_name}.eachLayer(function(layer) {{
            if (layer instanceof L.TileLayer) {{
                if (layer.options && layer.options.id) {{
                    tileLayers[layer.options.id] = layer;
                }}
            }}
        }});

        function switchTileLayer(tileName) {{
            for (var key in tileLayers) {{
                {map_name}.removeLayer(tileLayers[key]);
            }}
            if (tileLayers[tileName]) {{
                tileLayers[tileName].addTo({map_name});
            }} else {{
                console.error('Tile layer ' + tileName + ' not found.');
            }}
        }}

        function zoomToLocation(id) {{
            const loc = locations[id];
            if (loc) {{
                // Switch tile layer
                switchTileLayer(loc.tile_layer);

                // Fly to location
                {map_name}.flyTo([loc.lat, loc.lon], loc.zoom);
            }}
        }}

        function onMapClick(e) {{
            var lat = e.latlng.lat.toFixed(5);
            var lng = e.latlng.lng.toFixed(5);
            var latlngStr = lat + ', ' + lng;
            navigator.clipboard.writeText(latlngStr).then(function() {{
                alert('Coordinates ' + latlngStr + ' copied to clipboard.');
            }}, function(err) {{
                console.error('Could not copy text: ', err);
                alert('Could not copy coordinates to clipboard.');
            }});
        }}

        // Display zoom level indicator
        function updateZoomIndicator() {{
            var zoomLevel = {map_name}.getZoom();
            document.getElementById('zoom-indicator').innerText = 'Zoom Level: ' + zoomLevel;
        }}

        {map_name}.on('click', onMapClick);
        {map_name}.on('zoomend', updateZoomIndicator);
        updateZoomIndicator(); // Initial call

        // Expose zoomToLocation globally
        window.zoomToLocation = zoomToLocation;
    }}

    if (document.readyState === 'complete') {{
        initMapFunctions();
    }} else {{
        window.addEventListener('load', initMapFunctions);
    }}
    </script>
    """.format(
        map_name=map_name,
        locations_js=locations_js_str
    )

    # Navigation pane HTML
    nav_links = ''.join(
        '<a class="bookmark-link" href="#" onclick="zoomToLocation({}); return false;">{}</a>'.format(i, bookmark["title"])
        for i, bookmark in enumerate(bookmarks)
    )

    nav_html = """
    <div class="nav-pane">
        <h2>Bookmarks</h2>
        {nav_links}
    </div>
    """.format(nav_links=nav_links)

    # Zoom level indicator HTML
    zoom_indicator_html = """
    <div id="zoom-indicator" class="zoom-indicator"></div>
    """

    # Custom CSS
    custom_css = """
    <style>
    body {{
        margin: 0;
        padding: 0;
        display: flex;
        height: 100vh;
        width: 100vw;
        overflow: hidden;
    }}
    #{map_id} {{
        width: 80%;
        height: 100vh;
        flex-grow: 1;
        position: relative;
    }}
    .nav-pane {{
        width: 20%;
        min-width: 250px;
        height: 100vh;
        background: #fff;
        padding: 20px;
        overflow-y: auto;
        box-shadow: 2px 0 5px rgba(0,0,0,0.1);
        z-index: 1000;
    }}
    .bookmark-link {{
        display: block;
        padding: 10px;
        margin: 5px 0;
        background: #f0f0f0;
        border-radius: 4px;
        cursor: pointer;
        text-decoration: none;
        color: #333;
    }}
    .bookmark-link:hover {{
        background: #e0e0e0;
    }}
    .modal-content {{
        padding: 20px;
        background: white;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }}
    .zoom-indicator {{
        position: absolute;
        bottom: 10px;
        left: 10px;
        padding: 5px 10px;
        background: rgba(255, 255, 255, 0.8);
        border-radius: 4px;
        font-weight: bold;
    }}
    </style>
    """.format(map_id=map_name)

    # Add CSS, navigation pane, zoom indicator, and JavaScript to the map's HTML
    m.get_root().html.add_child(folium.Element(custom_css + nav_html + zoom_indicator_html + nav_js))

    return m

def save_map(bookmarks, output_file='presentation.html', center=[39.54316, -110.38948], zoom=3):
    """Save the map to an HTML file."""
    m = create_map(bookmarks, center, zoom)
    m.save(output_file)

def load_bookmarks(json_file):
    """Load bookmarks from a JSON file."""
    with open(json_file, 'r') as f:
        bookmarks = json.load(f)
    return bookmarks

# Example usage
if __name__ == "__main__":
    sample_bookmarks = load_bookmarks('bookmarks.json')
    save_map(sample_bookmarks, center=[39.54316, -110.38948], zoom=3)
