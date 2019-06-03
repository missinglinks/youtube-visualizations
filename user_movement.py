import os
import click
import json
from pyg.reader import YoutubeArchiveReader
from collections import defaultdict
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from provit import Provenance

def get_prov(filepath, channel_name):
    
    prov = Provenance(filepath)
    prov_data = prov.tree()
    return {
        "channel": channel_name,
        "retrieved_at": prov_data["ended_at"]
    }

def build_movement_dataset(directory):
    channels = []
    users = defaultdict(dict)
    years = set()
    provenance = []

    for filename in os.listdir(directory):
        if filename.endswith(".zip"):
            print("loading "+filename)

            filepath = os.path.join(directory,filename)

            channel = filename.replace(".zip","")
            channels.append(channel)

            #gather provenance information
            provenance.append(get_prov(filepath, channel))
            
            archive = YoutubeArchiveReader(filepath)

            # get the first comment per channel for each user
            for video in archive:
                for comment in video.comments:
                    years.add(int(comment["timestamp"][:4]))
                    user = comment["author_id"]
                    #print(comment["timestamp"])
                    if channel in users[user]:
                        if comment["timestamp"] < users[user][channel]['timestamp']:
                            users[user][channel] = {
                                'timestamp': comment['timestamp'],
                                'user_id': comment['author_id'],
                                'comment': comment['text'],
                                'video': video.title,
                                'video_id': video.id,
                                'user': comment['author']
                            }
                    else:
                        users[user][channel] = {
                                'timestamp': comment['timestamp'],
                                'user_id': comment['author_id'],
                                'comment': comment['text'],
                                'video': video.title,
                                'video_id': video.id,
                                'user': comment['author']
                            }

    #sort them by timestamp                   
    dataset = { id_: sorted(list(data.items()), key=lambda x:x[1]['timestamp']) for id_, data in users.items() }
    
    #generate nodes of user movements
    arcs = []
    for id_, data in dataset.items():
        
        first = data[0]
        for target in data[1:]:
        
            arcs.append({
                "first": first,
                "target": target,
            })
            

    simple = defaultdict(dict)
    incoming_ds = defaultdict(list)
    
    #generate edges (aggregate user movements per month)
    for arc in arcs:
        # build simplified arc dataset
        first_date = arc["first"][1]['timestamp'][:7]
        first_channel = arc["first"][0]
        target_date = arc["target"][1]['timestamp'][:7]
        target_channel = arc["target"][0]

        id_ = "{}__{}__{}__{}".format(first_date, first_channel, target_date, target_channel)
        if "value" in simple[id_]:
            simple[id_]["value"] += 1
        else:
            simple[id_] = {
                "first": (first_channel, first_date),
                "target": (target_channel, target_date),
                "value": 1
            }
            
        # build incoming dataset
        inc_id = first_channel+"__"+target_channel+"__"+target_date
        c = arc['target'][1]
        incoming_ds[inc_id].append(c)
        
    
    max_arc = max([ x["value"] for x in simple.values() ])
    
    
    incoming_final = {}
    
    for id_, data in incoming_ds.items():
        video_ds = defaultdict(list)
        for comment in data:
            video_ds[comment['video']].append([comment['user'], comment['comment']])
        
        incoming_final[id_] = {
            'count': len(data),
            'videos': sorted(list(video_ds.items()), key=lambda x: len(x[1]), reverse=True)
        }
    
    
    return {
        "years": sorted(list(years)),
        "channels": list(channels),
        "max": max_arc,
        "arcs": list(simple.values()),
        "incoming": list(incoming_final.items()),
        "provenance": provenance
    }
            


@click.command()
@click.option('--output','-o', default='output/user_movement.html')
def build_vis(output):

    outfile_dir = Path(output).parent
    if not outfile_dir.exists():
        outfile_dir.mkdir(parents=True)

    print('generate user movement datset ...')
    dataset = build_movement_dataset("data")

    print('generate visualisation html file ...')
    root = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(root, 'templates')
    env = Environment( loader = FileSystemLoader(templates_dir) )
    template = env.get_template('user_movement.html')

    with open(output, 'w') as f:
        f.write(template.render(
            dataset=repr(json.dumps(dataset))
        ))

if __name__ == '__main__':
    build_vis()