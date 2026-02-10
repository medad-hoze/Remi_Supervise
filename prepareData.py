
import os
import ast 

import pandas    as pd
import geopandas as gpd
import numpy as np


from arcgis.gis import GIS
from shapely    import Polygon, wkt
from utiles     import read_layer_to_gdf,create_compilation
from arcgis.features import FeatureSet


id_current   = '07d981b9fb364280bec5c79778fe6e5e'
id_lastMonth = '9f3bae6056a44a5bbd0275db5a87d7c7'




def creaete_random_changes(df_changedFull2):

    # for test only !!
    np.random.seed(42)  
    mask = df_changedFull2['mavat_name_current'] == 'קרקע חקלאית'
    indices = df_changedFull2[mask].index.tolist()

    n_to_change = int(len(indices) * 0.15)
    indices_to_change = np.random.choice(indices, size=n_to_change, replace=False)

    replacements = ["מגורים ד'", 'מגורים בישוב כפרי', 'מגורים א']

    df_changedFull2.loc[indices_to_change, 'mavat_name_current'] = np.random.choice(replacements, size=n_to_change)


    return df_changedFull2



def load_WKT(x):
    try:
        wkt_ = wkt.loads(x.WKT)
        if not wkt_.is_valid:
            wkt_ = wkt_.buffer(0)
    except Exception as e:
        print("Error with WKT:", e)
        print(x)
        wkt_ = x
    return wkt_





def check_added_deleted_parcels(gis, output_added, output_deleted, output_changed):
    
    item_current   = gis.content.get(id_current  )
    item_lastMonth = gis.content.get(id_lastMonth)

    df_current   = item_current  .layers[0].query(where='1=1').sdf
    df_lastMonth = item_lastMonth.layers[0].query(where='1=1').sdf

    df_current['GUSH'       ] = df_current['GUSH'       ].astype(str).str.replace('.0', '', regex=False)
    df_current['MisparHelka'] = df_current['MisparHelka'].astype(str).str.replace('.0', '', regex=False)

    df_lastMonth['GUSH'       ] = df_lastMonth['GUSH'       ].astype(str).str.replace('.0', '', regex=False)
    df_lastMonth['MisparHelka'] = df_lastMonth['MisparHelka'].astype(str).str.replace('.0', '', regex=False)

    df_current  ['key'] = df_current  ['GUSH'] + '_' + df_current  ['MisparHelka']
    df_lastMonth['key'] = df_lastMonth['GUSH'] + '_' + df_lastMonth['MisparHelka']

    # Find added and deleted parcels
    df_merged       = pd.merge(df_current, 
                               df_lastMonth[['key']],
                               on='key', how='outer', 
                               indicator=True)
    
    df_newRows      = df_merged[df_merged['_merge'] == 'left_only']
    df_deletedRows  = df_merged[df_merged['_merge'] == 'right_only']
    df_deletedRows  = df_lastMonth[df_lastMonth['key'].isin(df_deletedRows['key'])]
    df_newRows      = df_current  [df_current  ['key'].isin(df_newRows    ['key'])]

    # Find parcels where achuz_baalut_kkl or ShetachBaalutKKL changed
    df_common = pd.merge(
        df_current[['key', 'achuz_baalut_kkl', 'ShetachBaalutKKL', 'GUSH', 'MisparHelka', 'SHAPE']],
        df_lastMonth[['key', 'achuz_baalut_kkl', 'ShetachBaalutKKL', 'SHAPE']],
        on='key',
        suffixes=('_current', '_lastMonth')
    )
    
    df_changed = df_common[
        (df_common['achuz_baalut_kkl_current'] != df_common['achuz_baalut_kkl_lastMonth']) |
        (df_common['ShetachBaalutKKL_current'] != df_common['ShetachBaalutKKL_lastMonth'])
    ].copy()
    

    df_changed['Area_calc_lastMonth'] = df_changed['SHAPE_lastMonth'].apply(
        lambda x: wkt.loads(esri_rings_to_wkt(x)).area if x and esri_rings_to_wkt(x) else None
    )
    
    df_changedFull = df_current[df_current['key'].isin(df_changed['key'])].copy()
    df_changedFull = df_changedFull.merge(
        df_changed[['key', 'achuz_baalut_kkl_lastMonth', 
                    'ShetachBaalutKKL_lastMonth', 'Area_calc_lastMonth','SHAPE_lastMonth']],
        on='key'
    )

    # Save outputs
    df_newRows    .to_excel(output_added, index=False)
    df_deletedRows.to_excel(output_deleted, index=False)
    
    df_changedFull = df_changedFull.drop_duplicates(subset=['GUSH','MisparHelka'])
    if df_changedFull.empty:
        print("No changed parcels found.")
    else:
        df_changedFull.to_excel(output_changed, index=False)

    return df_newRows, df_deletedRows, df_changedFull




def esri_rings_to_wkt(rings_data):
    if pd.isna(rings_data) or rings_data is None:
        return Polygon().wkt  # Returns 'POLYGON EMPTY'
    
    if isinstance(rings_data, str):
        ring = ast.literal_eval(rings_data)
    else:
        ring = rings_data
    
    rings = ring.get('rings', [])
    
    if len(rings) == 0:
        return Polygon().wkt  # Returns 'POLYGON EMPTY'
    
    exterior_ring = rings[0]
    coord_strings = [f"{x} {y}" for x, y in exterior_ring]
    coords_wkt    = ", ".join(coord_strings)
    wkt_string    = f"POLYGON (({coords_wkt}))"
    
    return wkt_string



print ('start prepare data')

username = 'medadhozekkl'
password = 'medadhozekkl123'
org      = 'https://kkl.maps.arcgis.com/home'
gis      = GIS(org, username, password)


#######################################################################################

script_folder      = os.path.dirname(os.path.abspath(__file__))
output_added       = os.path.join(script_folder, 'added_reports.xlsx')
output_deleted     = os.path.join(script_folder, 'deleted_reports.xlsx')
output_changedFull = os.path.join(script_folder, 'changedFull_reports.xlsx')

data_folder    = os.path.dirname(script_folder) + '\\data'
if not os.path.exists(data_folder):
    os.makedirs(data_folder)

##########################  ייעודי קרקע   #####################################


# id_MAVAT = '4155083fb9944d7a9f528b9495c2c79a'

# item_mavat = gis.content.get(id_MAVAT)
# df_mavat   = item_mavat.layers[0].query(where='1=1').sdf

path_script = os.path.dirname(os.path.abspath(__file__))
path_main   = os.path.dirname(path_script)
path_data   = os.path.join(path_main, 'data')


gpkg_path  = r"C:\Users\medad\meidad\Work\KKL\compilation_mavat\data\compilation.gdb"
name_layer = 'PARCEL_ALL_WITH_MAVAT'

layer_mavat = gpkg_path + '\\' + name_layer

gdf_mavat_all   = read_layer_to_gdf(layer_mavat)

# if not os.path.exists(gpkg):

#     gdf_mavat = create_compilation(gdf_mavat_all, 'last_update_date')
#     gdf_mavat.to_file(gpkg, driver='GPKG', layer=name_comp)

# else:
#     print ('exists compilation')
#     gdf_mavat = gpd.read_file(gpkg, layer=name_comp)


# path_temp_compi = r'C:\Users\medad\meidad\Work\KKL\NetWork_Report\data\data.gdb\mavat_compilation'
# gdf_mavat = read_layer_to_gdf(path_temp_compi)



#######################################################################################


if os.path.exists(output_added) and os.path.exists(output_deleted) and os.path.exists(output_changedFull):

    df_newRows     = pd.read_excel(output_added)
    df_deletedRows = pd.read_excel(output_deleted)
    df_changedFull = pd.read_excel(output_changedFull)

else:
    df_newRows, df_deletedRows,df_changedFull = check_added_deleted_parcels(gis,output_added, 
                                                                            output_deleted,
                                                                            output_changedFull)





df_changedFull['achuz_baalut_kkl']   = pd.to_numeric(df_changedFull['achuz_baalut_kkl'], errors='coerce').fillna(0).astype(int)
df_changedFull['achuz_baalut_kkl_lastMonth'] = pd.to_numeric(df_changedFull['achuz_baalut_kkl_lastMonth'], errors='coerce').fillna(0).astype(int)

df_changedFull['ShetachBaalutKKL']  = pd.to_numeric(df_changedFull['ShetachBaalutKKL'], errors='coerce').fillna(0).astype(int)
df_changedFull['ShetachBaalutKKL_lastMonth'] = pd.to_numeric(df_changedFull['ShetachBaalutKKL_lastMonth'], errors='coerce').fillna(0).astype(int)

df_changedFull = df_changedFull[
    (abs(df_changedFull['achuz_baalut_kkl'] - df_changedFull['achuz_baalut_kkl_lastMonth']) > 1) |
    (abs(df_changedFull['ShetachBaalutKKL'] - df_changedFull['ShetachBaalutKKL_lastMonth']) > 10)
].copy()






df_deletedRows['WKT']       = df_deletedRows['SHAPE'].apply(lambda x: esri_rings_to_wkt(x))
df_newRows    ['WKT']       = df_newRows['SHAPE'].apply(lambda x: esri_rings_to_wkt(x))
df_changedFull['WKT']       = df_changedFull['SHAPE'].apply(lambda x: esri_rings_to_wkt(x))


df_newRows    ['Area_calc'] = df_newRows['WKT'].apply(lambda x: wkt.loads(x).area)
df_changedFull['Area_calc'] = df_changedFull['WKT'].apply(lambda x: wkt.loads(x).area)
df_deletedRows['Area_calc'] = df_deletedRows['WKT'].apply(lambda x: wkt.loads(x).area)


df_changedFull['Areakkl_total_lastMonth']     = df_changedFull['Area_calc_lastMonth'] * (df_changedFull['achuz_baalut_kkl_lastMonth'] / 100)
df_changedFull['Areakkl_total_current']       = df_changedFull['Area_calc'] * (df_changedFull['achuz_baalut_kkl'] / 100)

df_newRows['Areakkl_total_current']       = df_newRows['Area_calc'] * (df_newRows['achuz_baalut_kkl'] / 100)
df_newRows['Area_diff']                   = df_newRows['Areakkl_total_current']

df_deletedRows['Areakkl_total_current'] = 0
df_deletedRows['Areakkl_total_lastMonth'] = df_deletedRows['Area_calc'] * (df_deletedRows['achuz_baalut_kkl'] / 100)
df_deletedRows['Area_diff']               = df_deletedRows['Areakkl_total_lastMonth']


df_changedFull['Area_diff'] = df_changedFull['Areakkl_total_current'] - df_changedFull['Areakkl_total_lastMonth']
# if smaller then 1 sqm set to zero
df_changedFull.loc[df_changedFull['Area_diff'].abs() < 1, 'Area_diff'] = 0
df_changedFull['Area_diff'].sum()



df_newRows_geometry    = df_newRows[df_newRows['SHAPE'].notna()].copy()
df_newRows_NonGeometry = df_newRows[df_newRows['SHAPE'].isna()].copy()


df_deletedRows_geometry    = df_deletedRows[df_deletedRows['SHAPE'].notna()].copy()
df_deletedRows_NonGeometry = df_deletedRows[df_deletedRows['SHAPE'].isna()].copy()





df_newRows      ['key'] = df_newRows      ['GUSH'].astype(str) +'-' + df_newRows    ['MisparHelka'].astype(str) +'-0'
df_deletedRows  ['key'] = df_deletedRows  ['GUSH'].astype(str) +'-' + df_deletedRows['MisparHelka'].astype(str) +'-0'
df_changedFull  ['key'] = df_changedFull  ['GUSH'].astype(str) +'-' + df_changedFull  ['MisparHelka'].astype(str) +'-0'


df_changedFull['type_status'] = 'changed'
df_newRows     ['type_status'] = 'added'
df_deletedRows ['type_status'] = 'deleted'




df_data = pd.concat([df_changedFull, df_newRows, df_deletedRows], ignore_index=True)

gdf_mavat_all['GUSH_NUM']  = gdf_mavat_all['GUSH_NUM'].astype(str).str.replace('.0', '', regex=False)
gdf_mavat_all['PARCEL']    = gdf_mavat_all['PARCEL'].astype(str).str.replace('.0', '', regex=False)
gdf_mavat_all['key']       = gdf_mavat_all['GUSH_NUM'].astype(str) +'-' + gdf_mavat_all['PARCEL'].astype(str) +'-0'



map_data= gdf_mavat_all.set_index('key')['mavat_name'].to_dict()

df_data['mavat_name_current'  ] = df_data['key'].map(map_data)
df_data['mavat_name_lastMonth'] = df_data['key'].map(map_data)

####################  DELETE THIS only for test  ##########################
df_data = creaete_random_changes (df_data)
################################################################################


df_data['mavat_name_current'] = df_data['mavat_name_current'].fillna('לא ידוע')
df_data['mavat_name_lastMonth'] = df_data['mavat_name_lastMonth'].fillna('לא ידוע')

df_data['mavat_changed'] = df_data.apply(
    lambda row: row['mavat_name_current'] != row['mavat_name_lastMonth'], axis=1
)



df_data['mavat_name_current'].value_counts()
df_data['mavat_name_lastMonth'].value_counts()




dict_values = {
    'מגורים א'                : 10,
    'מגורים בישוב כפרי'      : 8,
    'מגורים ד'                : 6,
    'קרקע חקלאית'            : 1,
    'שטח פתוח'               : 2,
    'תעשיה ומלאכה'           : 7,
    'מסחר ושירותים'          : 9,
    'יעוד עפ"י תכנית מאושרת אחרת': 5,
    'מבנים ומוסדות ציבוריים'  : 4}

df_data['points_mavat_current']   = df_data['mavat_name_current'].map(dict_values).fillna(0)
df_data['points_mavat_lastMonth'] = df_data['mavat_name_lastMonth'].map(dict_values).fillna(0)

df_data['score_diff'] = (df_data['Areakkl_total_current'] * df_data['points_mavat_current']) - \
                                (df_data['Areakkl_total_lastMonth'] * df_data['points_mavat_lastMonth'])
                                                                                    




# make sure all flaot are round to 2 after and all none or nun are 0
df_data['points_mavat_current']   = df_data['points_mavat_current'].fillna(0).round(2)
df_data['points_mavat_lastMonth'] = df_data['points_mavat_lastMonth'].fillna(0).round(2)
df_data['score_diff'] = df_data['score_diff'].fillna(0).round(2)
df_data['Area_diff'] = df_data['Area_diff'].fillna(0).round(2)
df_data['Areakkl_total_current'] = df_data['Areakkl_total_current'].fillna(0).round(2)
df_data['Areakkl_total_lastMonth'] = df_data['Areakkl_total_lastMonth'].fillna(0).round(2)


df_data2 = df_data[
    (df_data['Area_diff'] != 0) |
    (df_data['achuz_baalut_kkl'] != df_data['achuz_baalut_kkl_lastMonth']) |
    (df_data['Areakkl_total_current'] != df_data['Areakkl_total_lastMonth']) |
    (df_data['mavat_changed'] == True)
].copy()


df_3 = df_data2[['HelkaMerhav','TeurShita','GUSH','MisparHelka'
                 ,'BaalutBefoal','MatzavRishum','ShetachBaalutKKL',
                 'Shape__Area','achuz_baalut_kkl', 'SHAPE', 'key',
                   'achuz_baalut_kkl_lastMonth','ShetachBaalutKKL_lastMonth',
                     'Area_calc_lastMonth', 'Area_calc','WKT',
                     'Areakkl_total_lastMonth', 'Areakkl_total_current', 'Area_diff',
                     'mavat_name_current', 'mavat_name_lastMonth', 'mavat_changed','score_diff',
                     'type_status']].copy()


# make new columns name WKT_84




df_3['geometry'] = df_3['WKT'].apply(
    lambda x: Polygon() if pd.isna(x) or not str(x).strip() else wkt.loads(x)
)
gdf_3            = gpd.GeoDataFrame(df_3, geometry='geometry', crs="EPSG:2039")
gdf_3            = gdf_3.to_crs(epsg=4326)

gdf_3.drop(columns=['SHAPE','WKT'], inplace=True)


gdf_3.to_file('data.geojson', driver='GeoJSON', encoding='utf-8')



gdf_3.columns


gdf_3[gdf_3['type_status'] == 'changed'][['ShetachBaalutKKL',
                                          'ShetachBaalutKKL_lastMonth',
                                          'achuz_baalut_kkl',
                                          'achuz_baalut_kkl_lastMonth']]




# df['geometry'] = df['SHAPE'].apply(lambda x: wkt.loads(esri_rings_to_wkt(x)))
# gdf            = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:2039")

# set gemetry crs 2039


# path_currreent = r'C:\Users\medad\meidad\Work\KKL\NetWork_Report\data\LAYERS.gpkg\PARCEL_ALL'
# gdf_currreent  = read_layer_to_gdf(path_currreent)
# gdf_current3   = gpd.overlay(gdf_currreent, gdf, how='intersection', keep_geom_type=True)


# gdf_current3.rename(columns={'BaalutBefoal_1':'BaalutBefoal'}, inplace=True)

# columns_to_remove = ['SHAPE','SHAPE_2','SHAPE_1']

# for col in columns_to_remove:
#     if col in gdf_current3.columns:
#         gdf_current3.drop(columns=[col], inplace=True, errors='ignore')
#     if col in gdf.columns:
#         gdf.drop(columns=[col], inplace=True, errors='ignore')


# gdf          .to_file(gpkg, driver='GPKG', layer='parcel_old')
# gdf_current3.to_file(gpkg , driver='GPKG', layer='parcel_current')


# #################  new parcels kkl  ###########################


# df_newRows2 = df_newRows[['HelkaMerhav','TeurShita','GUSH','MisparHelka','BaalutBefoal','MatzavRishum','ShetachBaalutKKL','isKklInBaalutBefoal']]
# gdf_newRows2 = gpd.GeoDataFrame(df_newRows2)
# gdf_newRows2.to_file(gpkg , driver='GPKG', layer='parcel_added')

# # id_current   = '07d981b9fb364280bec5c79778fe6e5e'
# # item_current = gis.content.get(id_current)
# # df_current   = item_current.layers[0].query(where='1=1').sdf



# # df_current['geometry'] = df_current['SHAPE'].apply(lambda x: load_WKT(x))
# # df_current             = df_current.drop(columns=['SHAPE'])
# # gdf_current            = gpd.GeoDataFrame(df_current, geometry='geometry', crs="EPSG:2039")


