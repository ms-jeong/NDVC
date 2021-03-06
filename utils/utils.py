import numpy as np
import torch
import os
from torch.nn import functional as F
from datetime import datetime
from dataset.cc_web_video import CC_WEB_VIDEO
from sklearn.metrics import precision_recall_curve, average_precision_score
import matplotlib.pyplot as plt
import cv2
from queue import Queue
import copy
import sys
import json
import logging.config
from datetime import datetime, timedelta


class AverageMeter(object):
    """Computes and stores the average and current value"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count


class MeasureMeter(object):

    def __init__(self):
        self.reset()

    def reset(self):
        self.tp = 0
        self.fp = 0
        self.fn = 0
        self.prec = 0
        self.rec = 0
        self.f1 = 0
        self.tot_tp = 0
        self.tot_fp = 0
        self.tot_fn = 0
        self.tot_rec = 0
        self.tot_rec = 0
        self.tot_f1 = 0
        self.cnt = 0

    def update(self, tp, fp, fn):
        self.tp = tp
        self.fp = fp
        self.fn = fn
        self.tot_tp += tp
        self.tot_fp += fp
        self.tot_fn += fn
        self.prec, self.rec, self.f1 = self.calc_f1_score(tp, fp, fn)
        self.tot_prec, self.tot_rec, self.tot_f1 = self.calc_f1_score(self.tot_tp, self.tot_fp, self.tot_fn)
        self.cnt += 1

    def calc_f1_score(self, tp, fp, fn, eps=1e-6):
        prec = tp / (tp + fp + eps)
        rec = tp / (tp + fn + eps)
        f1 = (2 * prec * rec) / (prec + rec + 1e-6)
        return prec, rec, f1

    def cnt_str(self):
        return 'TP: {}({}), FP: {}({}), FN: {}({})'.format(self.tp, self.tot_tp, self.fp, self.tot_fp, self.fn,
                                                           self.tot_fn)

    def precision_str(self):
        return '{:.4f}({:.4f})'.format(self.prec, self.tot_prec)

    def recall_str(self):
        return '{:.4f}({:.4f})'.format(self.rec, self.tot_rec)

    def f1_str(self):
        return '{:.4f}({:.4f})'.format(self.f1, self.tot_f1)

    def performance_str(self):
        return 'precision: {}, recall: {}, f-score: {}'.format(self.precision_str(), self.recall_str(), self.f1_str())

    def __str__(self):
        return '{} / {}'.format(self.performance_str(), self.cnt_str())


def kst(*args):
    return (datetime.now() + timedelta(hours=9)).timetuple()


def init_logger(desc='default'):
    def kst(*args):
        return (datetime.now() + timedelta(hours=9)).timetuple()

    time = datetime.now().strftime("%Y%m%d")
    config = json.load(open('log/logging.conf'))
    if not os.path.exists('log/{}'.format(time)):
        os.makedirs('log/{}'.format(time))
    config['handlers']['file']['filename'] = 'log/{}/{}.log'.format(time, desc)
    logging.config.dictConfig(config)
    logging.Formatter.converter = kst


def format_bytes(size):
    # 2**10 = 1024
    power = 2 ** 10
    n = 0
    power_labels = {0: '', 1: 'kilo', 2: 'mega', 3: 'giga', 4: 'tera'}
    while size > power:
        size /= power
        n += 1
    return size, power_labels[n] + 'bytes'


def int_round(f):
    return int(round(f))


def cosine_similarity_auto(query, features, cuda=True, numpy=True, query_split_cnt=200):
    score, idx, cos = cosine_similarity(query, features, cuda=cuda, numpy=numpy) \
        if query.shape[0] < query_split_cnt else cosine_similarity_split(query, features, cuda=cuda, numpy=numpy)
    return score, idx, cos


# multiple query
def cosine_similarity(query, features, cuda=True, numpy=True):
    if cuda:
        query = query.cuda()
        features = features.cuda()
    query = F.normalize(query, 2, 1)
    features = F.normalize(features, 2, 1)

    cos = torch.mm(features, query.t()).t()
    score, idx = torch.sort(cos, descending=True)

    post = lambda x: x.cpu().numpy() if numpy else x.cpu()

    score, idx, cos = map(post, [score, idx, cos])

    return score, idx, cos


def cosine_similarity_split(query, features, cuda=True, numpy=True):
    toCPU = lambda x: x.cpu()
    toNumpy = lambda x: x.numpy()
    q_l = query.split(100, dim=0)
    score_l = []
    cos_l = []
    idx_l = []
    if cuda:
        features = features.cuda()
    for q in q_l:
        if cuda: q = q.cuda()
        q = F.normalize(q, 2, 1)
        features = F.normalize(features, 2, 1)
        cos = torch.mm(features, q.t()).t()
        score, idx = torch.sort(cos, descending=True)
        score, idx, cos = map(toCPU, [score, idx, cos])

        cos_l.append(cos)
        score_l.append(score)
        idx_l.append(idx)

    cos = torch.cat(cos_l, dim=0)
    score = torch.cat(score_l, dim=0)
    idx = torch.cat(idx_l, dim=0)
    score, idx, cos = map(toNumpy, [score, idx, cos])

    return score, idx, cos


def cosine_similarity_split2(query, features):
    # nomalize
    query = F.normalize(query, 2, 1)
    features = F.normalize(features, 2, 1)

    q_l = query.split(100, dim=0)
    feature_l = features.split(5000, dim=0)
    for q in q_l:
        cos_l = []
        for f in feature_l:
            cos = torch.mm(f, q.t()).t()
            cos_l.append(cos)
        cos_l = torch.cat(cos_l, dim=0)
        score, idx = torch.sort(cos_l, descending=True)

        pass


def evaluate_mAP(indice, gt, k=[1, 500, 1000], pr_curve=False):
    aps = []
    ap_ks = []
    prs = []
    for i in range(len(gt)):
        ap, ap_k, pr = evaluate_AP(indice[i], gt[i], k, pr_curve)
        print(ap, ap_k)
        aps.append(ap)
        ap_ks.append(ap_k)
        prs.append(pr)

    aps = np.array(aps)
    ap_ks = np.array(ap_ks)
    if pr_curve:
        print(len(prs))
        for pr in prs[1:]:
            for id, r in enumerate(pr):
                prs[0][id][0] += r[0]
                prs[0][id][1] += r[1]
        prs = [p[0] / (p[1] + 1e-12) for p in prs[0]]

    else:
        prs = None
    mAP = aps.mean(axis=0)
    mAP_K = ap_ks.mean(axis=0)
    return mAP, mAP_K, prs


def evaluate_AP(indice, gt, k=[1, 500, 1000], pr_curve=False):
    indice = np.array(indice)
    gt = np.array(gt)
    # print(indice,len(gt))
    c = 0
    ap = 0.0
    ap_k = []
    re_c = [int(i * len(gt) * 0.04) for i in range(0, 26)]
    pr = []
    for i in range(26):
        pr.append([])
    for rank, idx in enumerate(indice, 1):
        # print(rank,c,len(gt))
        if c > len(gt): break
        if idx in gt:
            c += 1
            ap += (c / rank)
        if rank in k:
            ap_k.append(ap / c)
        if pr_curve and c in re_c:
            pr[re_c.index(c)].append(round(c / rank, 8))
    ap /= c
    while len(ap_k) != len(k):  ap_k.append(ap)
    if pr_curve:
        pr = [[sum(p), len(p)] for p in pr]

    return ap, ap_k, pr


def draw_pr_curve(pr):
    p = pr
    r = [i * 0.04 for i in range(0, 26)]
    plt.plot(r, p, 'b', label='Model')
    plt.legend(loc='upper right')
    plt.savefig('show/pr.jpg')


def cos_to_cv(cos, delimiter_idx, SCORE_THR, MIN_PATH):
    cos_im = (cos * 255).astype(np.uint8)
    cos_im[cos_im < SCORE_THR * 255] = 0
    lines = cv2.HoughLinesP(cos_im, 1, np.pi / 180, 1, MIN_PATH, 1)
    cos_im = cv2.cvtColor(cos_im, cv2.COLOR_GRAY2BGR)
    cos_im[:, delimiter_idx[:-1], 2] = 255

    return cos_im


def matching_gt(detection, gt):
    hit = 0
    iou = np.zeros((len(gt), len(detection)))
    for gi, g in enumerate(gt):
        for di, d in enumerate(detection):
            iou[gi][di] = (g[0].IOU(d[0]) + g[1].IOU(d[1])) * ((g[0].IOU(d[0]) * g[1].IOU(d[1])) > 0)
            # iou[gi][di] = (g[1].IOU(d[1])) * ((g[0].IOU(d[0]) * g[1].IOU(d[1])) > 0)
            # iou[gi][di] = (g[0].IOU(d[0])) * ((g[0].IOU(d[0]) * g[1].IOU(d[1])) > 0)

    while True:
        ind = np.unravel_index(np.argmax(iou, axis=None), iou.shape)
        if iou[ind] == 0: break
        # iou[ind[0],ind[1]] = 0
        iou[ind[0], :] = 0
        iou[:, ind[1]] = 0
        hit += 1
        # print(gt[ind[0]],detection[ind[1]])

    return hit


def calc_precision_recall_f1(tp, fp, fn, eps=1e-6):
    prec = tp / (tp + fp + eps)
    rec = tp / (tp + fn + eps)
    f1 = (2 * prec * rec) / (prec + rec + 1e-6)
    return prec, rec, f1


def matching_with_gt(detect, ground):
    name = detect['ref_vid']
    start = detect['ref'].start
    end = detect['ref'].end
    flag = False
    hit = None
    for i, gt in enumerate(ground):
        if name == gt['name'] and not (gt['end'] < start or end < gt['start']):
            hit = ground.pop(i)
            flag = True
            break
    return flag, hit


def match(detect, ground):
    hit = []
    hit_gt = []
    miss_detect = []
    for ndt, dt in enumerate(detect):
        flag = False
        dt_ref_name = dt['ref_name']
        dt_ref_start = dt['ref'].start
        dt_ref_end = dt['ref'].end
        for ngt, gt in enumerate(ground):
            if dt_ref_name == gt['ref_name'] and not (gt['ref'].end < dt_ref_start or dt_ref_end < gt['ref'].start):
                hit.append(dt)
                hit_gt.append(ground.pop(ngt))
                flag = True
                break
        if flag is False:
            miss_detect.append(dt)
    not_found = ground
    return hit, hit_gt, miss_detect, not_found


def matching(detected, ground):
    tp = []
    fn = []
    fp = []
    if not len(detected):
        fn = ground
    elif not len(ground):
        fp = detected
    else:
        hit_dt_idx = []
        for ig, gt in enumerate(ground):
            iou = np.zeros(len(detected))
            for id, dt in enumerate(detected):
                iou[id] = gt['ref'].IOU(dt['ref'])
            iou[hit_dt_idx] = 0
            if np.count_nonzero(iou) == 0:
                fn.append(gt)
            else:
                md = np.argmax(iou)
                tp.append((gt, detected[md]))
                hit_dt_idx.append(md)
        fp = [detected[i] for i in range(len(detected)) if i not in hit_dt_idx]

    return tp, len(tp), fp, len(fp), fn, len(fn)


if __name__ == '__main__':
    db = CC_WEB_VIDEO()
    dbl = db.get_VideoList(fmt=['videoid', 'queryid', 'status'])
    dbnp = np.array(dbl)
    l = np.array([v['VideoID'] for v in dbl])
    print(len(l))
    querys = db.get_Query()
    queryVids = np.array([q['VideoID'] for q in querys])
    print(l[:10])
    print(queryVids)

    print([np.where(l == q)[0][0] for q in queryVids])
    print(dbl[11458])

    feature = torch.load('/DB/CC_WEB_VIDEO/frame_1_per_sec/resnet50/v-feature.pt')
    print(feature.shape)

    fpath = '/DB/CC_WEB_VIDEO/frame_1_per_sec/resnet50/v-feature'
    l = os.listdir(fpath)
    l.sort(key=lambda x: int(x.split('.')[0]))
    vv = [torch.load(os.path.join(fpath, vf)) for vf in l]
    vv = torch.cat(vv)
    print(vv.shape)

    q = db.get_Query()
    qidx = [qi['index'] for qi in q]
    print(qidx)
    qv = vv[qidx].cuda()
    vv = vv.cuda()
    sc, idx = cosine_similarity(qv, vv)
    # print(db.get_VideoList(qid=1))

    # print(dbnp[idx[:, :100]])
    print(idx[:, :100])
    gt = db.get_reference_video_index(status='QESVML')
    evaluate_mAP(idx, gt)
