# For the Non-technical: What is highly dimensional sparse data?

*Andrew Morgan answered this question online ten years ago, before AI. His answer is reproduced here as he wrote it.*

I'll try and explain to a non technical audience, how they create high dimensional sparse data all the time, as this is an important concept.

Now, I'm sure you've been grocery shopping in a large supermarket, and I'll assume you've taken a look at your receipt.

This is highly dimensional sparse data.

The question is Why?

Each item on the shelves of the shop has a barcode. That's how you scan your shopping when you pay, right?

The electronic till and the scanner has a lookup table of bar codes, and that lookup table details out the numeric barcode, the human description of the product, the price it is sold at, and perhaps if it incurs sales tax, as well as other things. This could be quite large as it describes everything they sell in the shop.

Now, If I had all the receipt data for All customers, and I wanted to compare your shopping behaviour to other people, I would build the following very very large matrix

(which you can think of as a very big spreadsheet):

We have a column for each barcode. We have a row for each customer. This will be one Very Big spreadsheet! Imagine there are something like 300,000 barcodes in a large Walmart for example (columns). There might be 15 million customers (rows).

Now, getting back to your grocery receipt, imagine you scroll down to find your customer ID in that spreadsheet, then move across the columns putting in a zero if you didn't buy that product, or putting in the number items you did buy that has that same barcode.

You probably didn't buy 300,000 things on your trip shopping, so it's pretty obvious most of the cells would have a zero in them for you, and this is the case for everyone else too. If you bought 4 cans of soup, that one column for your row would have a count of 4 in the cell, meaning you bought 4 cans of that soup.

We use the word Sparse to describe this situation where most cells are zero for everyone. We use the phrase "highly dimensional" to refer to the very high number of columns (product).

That's how high dimensional sparse data is created by you all the time!

Our database allows us to search that dataset to find the person who is your nearest neighbour, meaning the person whose grocery basket is measurably the most similar to yours. We do it by calculating the cosine angle between your shopping vector and every other customer's. We can do this in milliseconds, even if there are 40 million customers and 350,000 dimensions, using some very complex mathematical tricks.

It means that UltraDim can detect near-duplicate neighbours, recommend products used by People-Like-You, identify anomalies (no near neighbours), build customer segmentations to tailor customer experience and do better CRM, and even classify changes in shopper behaviour over time as, perhaps, their stage of life changes.

And UltraDim does this on the native data, not a summary that degrades the analysis.

We can of course index AI datasets, meaning embeddings of text and documents, and do retrieval augmented search, which is what RAG means. But low dimensional data, under 10,000 dimensions, can be searched today with traditional tools. Our real value is in that new territory beyond it, where our tools give you the ability to make better strategic decisions.

## Where else is highly dimensional sparse data found?

This type of dataset is seen EVERYWHERE, and it is summarised into reports that hide the value.

Your genome. Customer data. Cyber data. IoT networks. Energy meter data. Digital twin data. Purchase transaction data. Supply chain data. Stock market data. Chemical datasets. Physics datasets. Drone and robot datasets, including onboard sensors. Movie choice data. Semantic search data. Weather data. The list is endless.

We imagine a future, a frontier, where computers and people collaborate, and our mission at Gamakon is to help you *Navigate the Frontier*.
