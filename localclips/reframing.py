"""Deterministic geometry shared by FFmpeg, still proxies and live Qt preview.

ROIs describe source pixels; each pane crops to its destination aspect before
scaling. Only the explicitly selected legacy 'fit' mode is letterboxed.
"""
import copy
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Placement:
    source: int
    crop: tuple[int, int, int, int]  # x, y, width, height in source pixels
    target: tuple[int, int, int, int]


def at_time(clip, timestamp):
    result = copy.deepcopy(clip)
    result.keyframes = []
    for key in clip.keyframes:
        if key['time'] > timestamp + 1e-6:
            break
        for name, value in key.items():
            if name != 'time':
                setattr(result, name, value)
    if result.layout in ('manual', 'dynamic'):
        result.layout = 'split'
    if clip.face_track:
        result.webcam[:2]=[track_value(clip.face_track,timestamp,axis) for axis in ('x','y')]
    return result


def track_value(points,t,axis):
    if t<=points[0]['time']: return points[0][axis]
    for a,b in zip(points,points[1:]):
        if t<=b['time']:
            s=(t-a['time'])/(b['time']-a['time'])
            return a[axis]+(b[axis]-a[axis])*s*s*(3-2*s)
    return points[-1][axis]


def track_expression(points,axis,scale,offset,time_origin):
    """Smoothstep interpolation matching track_value; crop uses even pixels."""
    expression=f"{points[-1][axis]*scale+offset:.6f}"
    for a,b in reversed(list(zip(points,points[1:]))):
        start,end=a['time']-time_origin,b['time']-time_origin
        s=f'clip((t-({start:.6f}))/{end-start:.6f},0,1)'
        v=f'({a[axis]*scale+offset:.6f}+({(b[axis]-a[axis])*scale:.6f})*{s}*{s}*(3-2*{s}))'
        expression=f'if(lt(t,{end:.6f}),{v},{expression})'
    return f'floor(({expression})/2)*2'


def fill_crop(media, rect, target_w, target_h, pan=(.5,.5), zoom=1.):
    x,y,w,h = rect
    rw,rh = w*media.width, h*media.height
    aspect = target_w/target_h
    cw = min(rw, rh*aspect)/zoom
    ch = cw/aspect
    # Integer even coordinates match FFmpeg yuv420 crop behavior. At most two
    # source pixels of aspect quantization, never anamorphic pane stretching.
    cw = max(2, int(cw)//2*2)
    ch = max(2, int(ch)//2*2)
    left = int((x*media.width+(rw-cw)*pan[0])/2)*2
    top = int((y*media.height+(rh-ch)*pan[1])/2)*2
    return max(0,min(left,media.width-cw)), max(0,min(top,media.height-ch)), cw,ch


class CompositionError(ValueError):
    pass


def intersects(a,b):
    return a[0]<b[0]+b[2] and b[0]<a[0]+a[2] and a[1]<b[1]+b[3] and b[1]<a[1]+a[3]


def overlay_bounds(media,clip,timestamp):
    """Conservative, constant obstacle per layout segment (never follows jitter)."""
    base=copy.deepcopy(clip)
    base.face_track=[]
    c=at_time(base,timestamp)
    rect=c.embedded_webcam
    if rect is None:
        if c.camera_path:
            return None  # an independent webcam is not implicitly on the desktop
        rect=c.webcam
    rectangles=[rect]
    # Old projects only stored the tracked face ROI. Cover its swept area too,
    # including interpolation extrema, instead of moving the screen crop.
    if c.embedded_webcam is None and clip.face_track:
        boundaries=sorted({clip.start,clip.end,*[k['time'] for k in clip.keyframes]})
        start=max(t for t in boundaries if t<=timestamp)
        end=next((t for t in boundaries if t>timestamp),clip.end)
        times=[start,end]+[p['time'] for p in clip.face_track if start<p['time']<end]
        rectangles += [[track_value(clip.face_track,t,'x'),track_value(clip.face_track,t,'y'),*c.webcam[2:]] for t in times]
    x=min(r[0] for r in rectangles)*media.width
    y=min(r[1] for r in rectangles)*media.height
    right=max(r[0]+r[2] for r in rectangles)*media.width
    bottom=max(r[1]+r[3] for r in rectangles)*media.height
    # A small guard covers interpolation/compression fringes. Outward even
    # rounding is essential: inward yuv420 rounding can leak the border.
    guard=max(4,math.ceil(min(media.width,media.height)*.004))
    left=max(0,math.floor((x-guard)/2)*2)
    top=max(0,math.floor((y-guard)/2)*2)
    right=min(media.width,math.ceil((right+guard)/2)*2)
    bottom=min(media.height,math.ceil((bottom+guard)/2)*2)
    return left,top,right-left,bottom-top


def screen_crop(media,rect,target_w,target_h,pan=(.5,.5),zoom=1.,obstacle=None):
    """Largest useful aspect crop in a free rectangle, without masks or padding.

    Preserve a valid user's crop exactly. Otherwise prioritize the selected ROI,
    area (less magnification), then proximity to the desired pan. If the ROI is
    entirely hidden/tiny, fall back to a nearby free region of the source.
    """
    wanted=fill_crop(media,rect,target_w,target_h,pan,zoom)
    if obstacle is None or not intersects(wanted,obstacle):
        return wanted
    ox,oy,ow,oh=obstacle
    free=[(0,0,ox,media.height),(ox+ow,0,media.width-ox-ow,media.height),
          (0,0,media.width,oy),(0,oy+oh,media.width,media.height-oy-oh)]
    wx,wy,ww,wh=wanted
    anchor=(wx+ww/2,wy+wh/2)
    def candidates(bounds):
        bx,by,bw,bh=bounds
        result=[]
        for fx,fy,fw,fh in free:
            x=math.ceil(max(fx,bx)/2)*2
            y=math.ceil(max(fy,by)/2)*2
            right=math.floor(min(fx+fw,bx+bw)/2)*2
            bottom=math.floor(min(fy+fh,by+bh)/2)*2
            if right-x<16 or bottom-y<16: continue
            region=[x/media.width,y/media.height,(right-x)/media.width,(bottom-y)/media.height]
            crop=fill_crop(media,region,target_w,target_h,pan,zoom)
            if min(crop[2:])<16 or intersects(crop,obstacle): continue
            cx,cy,cw,ch=crop
            area=cw*ch/(ww*wh)
            distance=math.hypot((cx+cw/2-anchor[0])/media.width,(cy+ch/2-anchor[1])/media.height)
            result.append((min(area,1)*.8-distance*.2,crop))
        return result
    bounds=(rect[0]*media.width,rect[1]*media.height,rect[2]*media.width,rect[3]*media.height)
    preferred=candidates(bounds)
    # Do not turn a sliver beside an overlay into an extreme automatic zoom.
    preferred=[p for p in preferred if p[1][2]*p[1][3]>=ww*wh*.20]
    options=preferred or candidates((0,0,media.width,media.height))
    if not options:
        raise CompositionError('La regione webcam copre tutto lo schermo utilizzabile. Correggi il rettangolo OBS da escludere.')
    return max(options,key=lambda p:p[0])[1]


def placements(media, clip, width=1080, height=1920, timestamp=None, camera=None):
    # Always derive crop geometry at the final canonical canvas size. Preview
    # output scales destinations only, so it cannot change the source framing.
    c = at_time(clip, clip.start if timestamp is None else timestamp)
    t=clip.start if timestamp is None else timestamp
    # Screen-only modes exclude a known OBS overlay too, keeping dynamic layout
    # changes consistent. Old unconfirmed screen projects keep their old crop.
    exclude=c.layout in ('split','pip') or c.webcam_confirmed or c.embedded_webcam is not None
    obstacle=overlay_bounds(media,clip,t) if exclude else None
    cw,ch=1080,1920
    regions=[]
    camera_media=camera or media
    cam_source=1 if camera else 0
    def pane(source, m, rect, dest, pan, zoom,screen=False):
        crop=screen_crop(m,rect,dest[2],dest[3],pan,zoom,obstacle) if screen else fill_crop(m,rect,dest[2],dest[3],pan,zoom)
        x,y,w,h=dest
        # Split boundaries use shared scaled coordinates, avoiding a one-pixel gap.
        x1,y1=round(x*width/cw),round(y*height/ch)
        x2,y2=round((x+w)*width/cw),round((y+h)*height/ch)
        regions.append(Placement(source,crop,(x1,y1,x2-x1,y2-y1)))
    if c.layout in ('split',):
        top=round(ch*c.split_ratio/2)*2
        pane(cam_source,camera_media,c.webcam,(0,0,cw,top),c.webcam_pan,c.webcam_zoom)
        pane(0,media,c.screen,(0,top,cw,ch-top),c.screen_pan,c.screen_zoom,screen=True)
    elif c.layout=='face':
        pane(cam_source,camera_media,c.webcam,(0,0,cw,ch),c.webcam_pan,c.webcam_zoom)
    elif c.layout in ('screen','crop','pip'):
        pane(0,media,c.screen,(0,0,cw,ch),[c.crop_x,.5] if c.layout=='crop' else c.screen_pan,c.screen_zoom,screen=True)
        if c.layout=='pip':
            pane(cam_source,camera_media,c.webcam,(720,90,324,432),c.webcam_pan,c.webcam_zoom)
    elif c.layout=='fit':
        # Explicit compatibility mode for old saved projects only.
        factor=min(cw/media.width,ch/media.height)
        w,h=int(media.width*factor)//2*2,int(media.height*factor)//2*2
        x,y=(cw-w)//2,(ch-h)//2
        regions.append(Placement(0,(0,0,media.width,media.height),
                                (round(x*width/cw),round(y*height/ch),round(w*width/cw),round(h*height/ch))))
    else:
        raise ValueError('Composizione non supportata.')
    return regions


def warnings(media,clip,camera=None):
    result=[]
    try:
        plan=placements(media,clip,camera=camera)
    except CompositionError as exc:
        return [str(exc)]
    for p in plan:
        upscale=max(p.target[2]/p.crop[2],p.target[3]/p.crop[3])
        if upscale>2.5:
            result.append(f'Ingrandimento {upscale:.1f}×: il ritaglio {p.crop[2]}×{p.crop[3]} può perdere dettaglio.')
    if clip.layout in ('split','face','pip','manual','dynamic') and not clip.webcam_confirmed:
        result.append('Regione webcam da confermare manualmente o tramite rilevamento affidabile.')
    c=at_time(clip,clip.start)
    index=1 if c.layout=='split' else 0
    if c.layout in ('split','pip','screen','crop'):
        p=plan[index]
        raw=fill_crop(media,c.screen,p.target[2],p.target[3],c.screen_pan if c.layout!='crop' else [c.crop_x,.5],c.screen_zoom)
        if raw!=p.crop:
            result.append('Area schermo adattata per escludere la webcam OBS. Regola area, zoom e posizione per scegliere il contenuto.')
    return result


def filter_graph(media,clip,width=1080,height=1920,camera=None):
    if (width,height)!=(1080,1920):
        graph=filter_graph(media,clip,1080,1920,camera)
        return graph.removesuffix('[base]')+'[fullcanvas];[fullcanvas]scale='+str(width)+':'+str(height)+'[base]'
    points=sorted(set([clip.start]+[k['time'] for k in clip.keyframes if clip.start<k['time']<clip.end]+[clip.end]))
    plans=[placements(media,clip,width,height,a,camera) for a in points[:-1]]
    flat=[(i,p) for i,plan in enumerate(plans) for p in plan]
    pieces=[]
    labels={}
    for source in set(p.source for _,p in flat):
        uses=[(i,j) for i,plan in enumerate(plans) for j,p in enumerate(plan) if p.source==source]
        tags=[f's{source}_{i}_{j}' for i,j in uses]
        if len(tags)==1:
            pieces.append(f'[{source}:v]null[{tags[0]}]')
        else:
            pieces.append(f'[{source}:v]split={len(tags)}'+''.join(f'[{s}]' for s in tags))
        labels.update({(i,j):tag for (i,j),tag in zip(uses,tags)})
    for i,plan in enumerate(plans):
        a,b=points[i]-clip.start,points[i+1]-clip.start
        c=at_time(clip,points[i])
        for j,p in enumerate(plan):
            x,y,w,h=p.crop
            dx,dy,dw,dh=p.target
            # force_original_aspect_ratio + final crop removes rounding edges,
            # while preserving proportional scaling at all resolutions.
            transform=f'crop={w}:{h}:{x}:{y},scale={dw}:{dh}:force_original_aspect_ratio=increase,crop={dw}:{dh},setsar=1'
            is_camera=(c.layout in ('split','face') and j==0) or (c.layout=='pip' and j==1)
            if clip.face_track and is_camera:
                m=camera or media
                # crop pan/zoom adds a constant displacement inside the moving ROI.
                rw,rh=c.webcam[2]*m.width,c.webcam[3]*m.height
                xexpr=track_expression(clip.face_track,'x',m.width,(rw-w)*c.webcam_pan[0],points[i])
                yexpr=track_expression(clip.face_track,'y',m.height,(rh-h)*c.webcam_pan[1],points[i])
                transform=f"crop={w}:{h}:x='{xexpr}':y='{yexpr}',scale={dw}:{dh}:force_original_aspect_ratio=increase,crop={dw}:{dh},setsar=1"
            if c.layout=='fit':
                transform+=f',pad={width}:{height}:{dx}:{dy}:color=0x10151e'
            pieces.append(f'[{labels[i,j]}]trim=start={a:.6f}:end={b:.6f},setpts=PTS-STARTPTS,{transform}[p{i}_{j}]')
        if len(plan)==1:
            pieces.append(f'[p{i}_0]null[v{i}]')
        elif c.layout=='pip':
            dx,dy,_,_=plan[1].target
            pieces.append(f'[p{i}_0][p{i}_1]overlay={dx}:{dy}:shortest=1[v{i}]')
        else:
            pieces.append(f'[p{i}_0][p{i}_1]vstack=inputs=2:shortest=1[v{i}]')
    if len(plans)==1:
        pieces.append('[v0]null[base]')
    else:
        pieces.append(''.join(f'[v{i}]' for i in range(len(plans)))+f'concat=n={len(plans)}:v=1:a=0[base]')
    return ';'.join(pieces)
